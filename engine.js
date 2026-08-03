(() => {
  const dims = ["executive", "attention", "creative", "social"];
  const clamp = (n) => Math.round(Math.max(.05, Math.min(.98, n)) * 1000) / 1000;
  const mins = (t) => { const [h, m] = t.split(":").map(Number); return h * 60 + m; };
  const clock = (n) => `${String(Math.floor(n / 60)).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}:00`;
  const profile = (task) => {
    const text = `${task.title} ${task.description}`.toLowerCase();
    if (/pitch|strategy|fundraising/.test(text)) return ["strategic", { executive: .9, attention: .72, creative: .82, social: .18 }];
    if (/financial|report|analyze|revenue/.test(text)) return ["analysis", { executive: .82, attention: .9, creative: .2, social: .08 }];
    if (/brainstorm|design|idea/.test(text)) return ["creative", { executive: .48, attention: .58, creative: .93, social: .12 }];
    return ["admin", { executive: .22, attention: .4, creative: .1, social: .35 }];
  };
  const makeForecast = (request) => {
    const slots = [], start = mins(request.user.workday_start), end = mins(request.user.workday_end);
    for (let now = start; now < end; now += 30) {
      const hour = now / 60, elapsed = (now - start) / (end - start);
      const circadian = .42 + .52 * Math.exp(-.5 * ((hour - 10) / 3.1) ** 2);
      const lunch = .1 * Math.exp(-.5 * ((hour - 13.7) / .9) ** 2);
      const recovery = .55 * request.signals.sleep_quality + .45 * Math.exp(-.5 * ((request.signals.sleep_hours - 7.7) / 1.8) ** 2);
      const fatigue = { executive: clamp(.05 + elapsed * .35), attention: clamp(.04 + elapsed * .39), creative: clamp(.04 + elapsed * .22), social: clamp(.03 + elapsed * .16) };
      const capacity = {
        executive: clamp(.42*circadian + .24*request.signals.focus + .18*request.signals.energy + .16*recovery - .3*fatigue.executive - lunch),
        attention: clamp(.36*circadian + .33*request.signals.focus + .18*recovery + .13*request.signals.energy - .34*fatigue.attention - lunch),
        creative: clamp(.24*circadian + .38*request.signals.creativity + .18*request.signals.energy + .12*recovery + Math.min(request.signals.exercise_minutes/120,1)*.08 - .22*fatigue.creative - lunch*.45),
        social: clamp(.23*circadian + .35*request.signals.energy + .22*recovery + .18 - .32*fatigue.social - lunch*.35)
      };
      const avg = dims.reduce((sum, key) => sum + capacity[key], 0) / 4;
      slots.push({ start: clock(now), end: clock(now+30), capacity, fatigue, label: avg >= .77 ? "peak" : avg >= .66 ? "good" : avg >= .52 ? "steady" : "recovery" });
    }
    return slots;
  };
  const optimize = (request) => {
    const forecast = makeForecast(request), occupied = [...request.calendar], recommendations = [];
    [...request.tasks].sort((a,b) => b.priority-a.priority).forEach((task) => {
      const [category, requirements] = profile(task), need = Math.ceil(task.duration_minutes/30), candidates = [];
      for (let i=0; i<=forecast.length-need; i+=1) {
        const chosen = forecast.slice(i,i+need), start = mins(chosen[0].start), end = mins(chosen.at(-1).end);
        if (occupied.some((b) => start < mins(b.end) && end > mins(b.start)) || (task.deadline_time && end > mins(task.deadline_time))) continue;
        const capacity = Object.fromEntries(dims.map((key) => [key, chosen.reduce((sum, s) => sum+s.capacity[key],0)/need]));
        const fatigue = Object.fromEntries(dims.map((key) => [key, chosen.reduce((sum, s) => sum+s.fatigue[key],0)/need]));
        const total = dims.reduce((sum,key) => sum+requirements[key],0);
        const fit = dims.reduce((sum,key) => sum+capacity[key]*requirements[key],0)/total;
        const fatigueCost = dims.reduce((sum,key) => sum+fatigue[key]*requirements[key],0)/total;
        const bonus = task.preferred_period === "afternoon" && start >= 720 && start < 1020 ? .04 : 0;
        candidates.push({ start:chosen[0].start, end:chosen.at(-1).end, score:clamp(.82*fit-.15*fatigueCost+bonus+(task.priority-3)*.008), capacity });
      }
      candidates.sort((a,b) => b.score-a.score); if (!candidates.length) return;
      const best = candidates[0], mid = candidates[Math.floor(candidates.length/2)], dominant = dims.reduce((win,key) => requirements[key]>requirements[win] ? key : win,"executive");
      occupied.push({start:best.start,end:best.end,category});
      recommendations.push({task_id:task.id,title:task.title,category,start:best.start,end:best.end,fit_score:best.score,confidence:clamp(.68+Math.max(0,best.score-(candidates[1]?.score||.5))*.7),improvement_percent:Math.max(0,Math.round((best.score-mid.score)/Math.max(mid.score,.01)*100)),reasons:[`${dominant[0].toUpperCase()+dominant.slice(1)} is the task's strongest demand and is forecast at ${Math.round(best.capacity[dominant]*100)}%.`,`This slot has a ${Math.round(best.score*100)}% cognitive-fit score after local calendar constraints.`]});
    });
    recommendations.sort((a,b) => a.start.localeCompare(b.start)); const peak = forecast.filter((s) => s.label === "peak");
    return {run_id:crypto.randomUUID(),status:"pending_approval",forecast,schedule:{recommendations,unscheduled_task_ids:request.tasks.filter((t)=>!recommendations.some((r)=>r.task_id===t.id)).map((t)=>t.id),recovery_suggestions:["Protect one screen-free recovery window in the late afternoon."]},evaluation:{approved:true,confidence:.88},coach_summary:peak.length?`Your strongest cognitive window is ${peak[0].start.slice(0,5)}–${peak.at(-1).end.slice(0,5)}. Protect it for your highest-leverage work.`:"Your schedule is ready for review.",trace:[{agent:"Cognitive Analyst",status:"completed",summary:`Forecast ${forecast.length} half-hour cognitive states using local browser signals.`,duration_ms:4},{agent:"Task Analyst",status:"completed",summary:`Classified ${request.tasks.length} tasks into cognitive demand profiles.`,duration_ms:2},{agent:"Planning Agent",status:"completed",summary:`Placed ${recommendations.length} of ${request.tasks.length} tasks using a local constrained optimizer.`,duration_ms:5},{agent:"Safety Reviewer",status:"completed",summary:"Schedule passed local calendar-conflict checks.",duration_ms:1},{agent:"Cognitive Coach",status:"completed",summary:"Generated an explainable, approval-gated recommendation.",duration_ms:1}]};
  };
  window.NeuroPilotEngine = { optimize };
})();

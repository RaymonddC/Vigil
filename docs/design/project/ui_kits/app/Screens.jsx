// Roster (default view), Patient detail, Alert detail, Alerts queue, Timeline, Settings

function Roster({ patients, onOpen }) {
  // sort: risk desc, then bed asc
  const order = { critical:0, high:1, medium:2, low:3, normal:4 };
  const sorted = [...patients].sort((a,b)=> order[a.risk]-order[b.risk] || a.bed.localeCompare(b.bed));
  return (
    <div className="page">
      <div className="page__hd">
        <h1 className="page__title">Roster</h1>
        <span className="page__sub">Ward 4N · 8 patients · sorted by risk</span>
        <span style={{marginLeft:'auto'}}><Button size="sm"><Icon name="filter" size={14}/>Filter</Button></span>
      </div>
      <div className="roster">
        <div className="roster__hd">
          <div></div>
          <div>Bed</div>
          <div>Patient</div>
          <div>Risk</div>
          <div className="col-alert">Latest alert</div>
          <div className="col-vitals">HR · MAP · SpO₂</div>
          <div className="col-ward">Ward</div>
        </div>
        {sorted.map(p => (
          <div key={p.id} className="roster__row" onClick={()=>onOpen(p.id)} tabIndex={0}
               onKeyDown={e=>(e.key==='Enter')&&onOpen(p.id)}>
            <RiskStripe level={p.risk}/>
            <div className="roster__bed">{p.bed}</div>
            <div className="roster__name">{p.name}<span className="mrn">MRN {p.mrn} · {p.day}</span></div>
            <div><RiskChip level={p.risk}/></div>
            <div className="col-alert roster__alert">{p.alert}{p.alertTime!=='—' && <span className="time">{p.alertTime}</span>}</div>
            <div className={`col-vitals roster__vitals ${p.risk==='critical'||p.risk==='high'?'bad':''}`}>
              {p.vitals.hr} · {p.vitals.map} · {p.vitals.spo2}
            </div>
            <div className="col-ward roster__ward">{p.ward}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PatientDetail({ patient, onBack, onOpenAlert, currentClinician, approvedMap, onApprove }) {
  const approved = !!approvedMap[patient.id];
  return (
    <div className="page">
      <div className="page__hd">
        <Button variant="ghost" onClick={onBack}><Icon name="arrow-left" size={14}/>Roster</Button>
        <h1 className="page__title">{patient.bed} · {patient.name}</h1>
        <RiskChip level={patient.risk}/>
        <span className="page__sub">MRN {patient.mrn} · {patient.ward} · {patient.day}</span>
      </div>
      <div className="pdetail">
        <div style={{display:'flex', flexDirection:'column', gap:16}}>
          <VitalsChart patient={patient}/>
          <Panel title="Comorbidities" meta={`${patient.comorbid.length} on file`}>
            <div className="panel__body" style={{display:'flex', gap:6, flexWrap:'wrap'}}>
              {patient.comorbid.length===0 ? <span style={{color:'var(--fg-3)', fontSize:12}}>None recorded</span> :
                patient.comorbid.map(c =>
                  <span key={c} style={{fontSize:12, padding:'3px 8px', border:'1px solid var(--border-subtle)', borderRadius:4, color:'var(--fg-2)'}}>{c}</span>
                )}
            </div>
          </Panel>
          <Panel title="Risk reasoning" meta="why Vigil flagged">
            <div className="reason">
              <div className="score">
                <span className="val" style={{color: `var(--risk-${patient.risk})`}}>
                  {patient.risk==='critical'?'8':patient.risk==='high'?'6':patient.risk==='medium'?'4':patient.risk==='low'?'2':'0'}
                </span>
                <span className="lbl">/ 12 · NEWS2</span>
              </div>
              <ul>
                {(patient.reasoning || ['Within normal limits — routine monitoring']).map((r,i)=><li key={i}>{r}</li>)}
              </ul>
            </div>
          </Panel>
        </div>
        <div style={{display:'flex', flexDirection:'column', gap:16}}>
          {patient.risk!=='normal' && patient.risk!=='low' ? (
            <>
              <SBARCard patient={patient} approved={approved} approver={currentClinician}/>
              <ApproveBar
                approved={approved}
                approver={currentClinician}
                onApprove={()=>onApprove(patient.id)}
                onDismiss={()=>{}}
              />
            </>
          ) : (
            <Panel title="No active alert">
              <div className="empty">Vigil is watching. Vitals within normal limits.</div>
            </Panel>
          )}
          <Panel title="Recent alerts">
            <div className="panel__body" style={{display:'flex', flexDirection:'column', gap:6, fontSize:12}}>
              <div style={{display:'flex', justifyContent:'space-between', padding:'4px 0', color:'var(--fg-2)'}}>
                <span>14:02 · Rising lactate</span><span style={{fontFamily:'var(--font-mono)', color:'var(--fg-3)'}}>CRITICAL</span>
              </div>
              <div style={{display:'flex', justifyContent:'space-between', padding:'4px 0', color:'var(--fg-2)'}}>
                <span>09:12 · Temp spike</span><span style={{fontFamily:'var(--font-mono)', color:'var(--fg-3)'}}>MEDIUM · dismissed</span>
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function AlertsQueue({ patients, onOpen }) {
  const active = patients.filter(p => p.risk==='critical' || p.risk==='high' || p.risk==='medium');
  return (
    <div className="page">
      <div className="page__hd">
        <h1 className="page__title">Pending alerts</h1>
        <span className="page__sub">{active.length} awaiting review · across 2 wards</span>
      </div>
      <div className="alerts-list">
        {active.map(p => (
          <div key={p.id} className="alert-card" onClick={()=>onOpen(p.id)}>
            <RiskChip level={p.risk}/>
            <div>
              <div className="who">{p.name}<span className="bed">· {p.bed} · {p.ward}</span></div>
              <div className="msg">{p.alert}</div>
            </div>
            <div className="meta">flagged {p.alertTime}<br/><span style={{color:'var(--fg-2)'}}>→ review</span></div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Timeline({ onTick }) {
  const [trace, setTrace] = React.useState(SEED_TRACE);
  React.useEffect(() => {
    const iv = setInterval(() => {
      setTrace(t => t); // keep alive (real app would poll)
    }, 2000);
    return () => clearInterval(iv);
  }, []);
  const handleTick = () => {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2,'0');
    const mm = String(now.getMinutes()).padStart(2,'0');
    const ss = String(now.getSeconds()).padStart(2,'0');
    const t = `${hh}:${mm}:${ss}`;
    setTrace(prev => {
      const last = prev.map(e => ({...e, done:true, active:false, ms: e.ms ?? 512}));
      return [...last, { t, state:'POLLING', detail:'fetching FHIR vitals', ms:null, done:false, active:true }];
    });
  };
  return (
    <div className="page">
      <div className="page__hd">
        <h1 className="page__title">Agent timeline</h1>
        <span className="page__sub">7-state machine · polling every 2 s</span>
        <span style={{marginLeft:'auto'}}>
          <Button variant="primary" onClick={handleTick}>Tick now</Button>
        </span>
      </div>
      <div className="trace">
        <div className="trace__hd">
          <span className="live"><span className="dot"></span>LIVE</span>
          <span className="s" style={{color:'var(--fg-3)', fontFamily:'var(--font-mono)', fontSize:11}}>
            next poll in 1.2s
          </span>
        </div>
        {trace.map((e, i) => (
          <div key={i} className={`evt ${e.done?'done':''} ${e.active?'active':''}`}>
            <span className="t">{e.t}</span>
            <span className="dot"></span>
            <span>
              <span className="lbl">{e.state}</span>
              <span className="detail">{e.detail}</span>
            </span>
            <span className="ms">{e.ms ? e.ms+' ms' : '—'}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Settings() {
  return (
    <div className="page">
      <div className="page__hd">
        <h1 className="page__title">System health</h1>
        <span className="page__sub">all green · last check 14:02:11</span>
      </div>
      <div className="settings-grid">
        <Panel title="LLM provider">
          <div>
            <div className="sysrow"><span className="k">Provider</span><span className="v">claude-sonnet-4.5</span></div>
            <div className="sysrow"><span className="k">Region</span><span className="v">us-east-1 · HIPAA BAA</span></div>
            <div className="sysrow"><span className="k">p50 latency</span><span className="v">412 ms</span></div>
            <div className="sysrow"><span className="k">Status</span><span className="status status--ok"><span className="d"></span>OPERATIONAL</span></div>
          </div>
        </Panel>
        <Panel title="FHIR gateway">
          <div>
            <div className="sysrow"><span className="k">Endpoint</span><span className="v">ehr.hospital.internal:8443</span></div>
            <div className="sysrow"><span className="k">Last sync</span><span className="v">14:02:08 · 220 ms</span></div>
            <div className="sysrow"><span className="k">Queue depth</span><span className="v">0</span></div>
            <div className="sysrow"><span className="k">Status</span><span className="status status--ok"><span className="d"></span>OPERATIONAL</span></div>
          </div>
        </Panel>
        <Panel title="Agent heartbeat">
          <div>
            <div className="sysrow"><span className="k">Poll interval</span><span className="v">2.0 s</span></div>
            <div className="sysrow"><span className="k">Uptime</span><span className="v">12d 4h 22m</span></div>
            <div className="sysrow"><span className="k">Last tick</span><span className="v">14:02:11</span></div>
            <div className="sysrow"><span className="k">Status</span><span className="status status--ok"><span className="d"></span>HEARTBEAT</span></div>
          </div>
        </Panel>
        <Panel title="Review queue">
          <div>
            <div className="sysrow"><span className="k">Pending</span><span className="v">3 alerts</span></div>
            <div className="sysrow"><span className="k">Oldest</span><span className="v">14 min</span></div>
            <div className="sysrow"><span className="k">Attributable</span><span className="v">100 %</span></div>
            <div className="sysrow"><span className="k">SLA</span><span className="status status--warn"><span className="d"></span>WATCH</span></div>
          </div>
        </Panel>
      </div>
    </div>
  );
}

Object.assign(window, { Roster, PatientDetail, AlertsQueue, Timeline, Settings });

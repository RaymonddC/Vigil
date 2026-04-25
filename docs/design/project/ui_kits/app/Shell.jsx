// Top-level Shell: nav, routing, clinician switcher, theme toggle

function ClinicianSwitcher({ current, onChange }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="cliswitcher">
      <button className="clipill" onClick={()=>setOpen(o=>!o)}>
        <span className="av">{current.initials}</span>
        <span>{current.name}</span>
        <span className="role">{current.role}</span>
      </button>
      {open && (
        <div className="cliswitcher__menu" role="menu">
          {CLINICIANS.map(c => (
            <button key={c.id}
              onClick={()=>{ onChange(c); setOpen(false); }}
              style={{display:'flex', alignItems:'center', gap:10, padding:'8px 12px', width:'100%',
                      background: c.id===current.id?'var(--surface-2)':'transparent',
                      border:'none', cursor:'pointer', textAlign:'left', fontFamily:'var(--font-sans)', fontSize:12}}>
              <span style={{width:22,height:22,borderRadius:'50%',background:'var(--gray-200)',color:'var(--fg-2)',
                             display:'flex',alignItems:'center',justifyContent:'center',fontSize:10,fontWeight:600}}>
                {c.initials}
              </span>
              <span style={{color:'var(--fg-1)', flex:1}}>{c.name}</span>
              <span style={{fontFamily:'var(--font-mono)', fontSize:10, color:'var(--fg-3)', textTransform:'uppercase', letterSpacing:'0.06em'}}>
                {c.role}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ThemeToggle({ dark, onToggle }) {
  return (
    <button className="btn btn--ghost" onClick={onToggle} aria-label="Toggle theme" title="Toggle theme">
      <Icon name={dark?'sun':'moon'} size={14}/>
    </button>
  );
}

function Toast({ msg }) {
  if (!msg) return null;
  return (
    <div style={{
      position:'fixed', bottom:20, right:20, zIndex:100,
      background:'var(--success-bg)', color:'var(--success)',
      border:'1px solid color-mix(in oklab, var(--success) 40%, transparent)',
      borderRadius:6, padding:'10px 14px', fontSize:13, fontWeight:500,
      display:'flex', alignItems:'center', gap:10,
      boxShadow:'var(--shadow-sm)',
      animation:'slideIn 180ms ease-out'
    }}>
      <Icon name="check-check" size={16}/>{msg}
    </div>
  );
}

function App() {
  const [route, setRoute] = React.useState({ name: 'roster' });
  const [currentClinician, setCurrentClinician] = React.useState(CLINICIANS[2]); // Dr. Patel
  const [dark, setDark] = React.useState(false);
  const [approvedMap, setApprovedMap] = React.useState({});
  const [toast, setToast] = React.useState(null);

  React.useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
  }, [dark]);

  const openPatient = (id) => setRoute({ name:'patient', id });
  const back = () => setRoute({ name:'roster' });

  const handleApprove = (patientId) => {
    setApprovedMap(m => ({ ...m, [patientId]: currentClinician.id }));
    const p = PATIENTS.find(pp => pp.id===patientId);
    setToast(`Handoff written to EHR for ${p.bed}.`);
    setTimeout(() => setToast(null), 3200);
  };

  const tabs = [
    { id:'roster',    label:'Roster',    icon:'users-round',  route:{name:'roster'} },
    { id:'alerts',    label:'Alerts',    icon:'bell',         route:{name:'alerts'} },
    { id:'timeline',  label:'Timeline',  icon:'activity',     route:{name:'timeline'} },
    { id:'marketplace',label:'Marketplace', icon:'store',     route:{name:'marketplace'} },
    { id:'settings',  label:'Settings',  icon:'settings',     route:{name:'settings'} },
  ];

  let body;
  const currentPatient = route.name==='patient' ? PATIENTS.find(p=>p.id===route.id) : null;
  if (route.name==='roster')     body = <Roster patients={PATIENTS} onOpen={openPatient}/>;
  else if (route.name==='patient') body = <PatientDetail patient={currentPatient} onBack={back} currentClinician={currentClinician} approvedMap={approvedMap} onApprove={handleApprove}/>;
  else if (route.name==='alerts') body = <AlertsQueue patients={PATIENTS} onOpen={openPatient}/>;
  else if (route.name==='timeline') body = <Timeline/>;
  else if (route.name==='settings') body = <Settings/>;
  else if (route.name==='marketplace') body = <Marketplace/>;

  const activeTab = route.name === 'patient' ? 'roster' : route.name;

  return (
    <>
      <nav className="nav">
        <div className="nav__brand">
          <svg width="22" height="22" viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <path d="M6 5 L26 5 L26 16 C26 22.6 21.5 27 16 29 C10.5 27 6 22.6 6 16 Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
            <path d="M10.5 16 C12.2 13.3 14 12 16 12 C18 12 19.8 13.3 21.5 16 C19.8 18.7 18 20 16 20 C14 20 12.2 18.7 10.5 16 Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
            <circle cx="16" cy="16" r="1.75" fill="currentColor"/>
          </svg>
          <span className="wm">Vigil</span>
        </div>
        <div className="nav__tabs">
          {tabs.map(t => (
            <button key={t.id} className={`nav__tab ${activeTab===t.id?'nav__tab--active':''}`} onClick={()=>setRoute(t.route)}>
              <Icon name={t.icon} size={14}/>{t.label}
            </button>
          ))}
        </div>
        <div className="nav__right">
          <ThemeToggle dark={dark} onToggle={()=>setDark(d=>!d)}/>
          <ClinicianSwitcher current={currentClinician} onChange={setCurrentClinician}/>
        </div>
      </nav>
      {body}
      <Toast msg={toast}/>
    </>
  );
}

function Marketplace() {
  const listings = [
    { name:'vigil-clinical-tools', type:'MCP Tool Library', author:'Vigil Health',
      desc:'FHIR read, NEWS2/qSOFA scoring, SBAR drafter, audit log writer. 12 tools, versioned.',
      installs:'2.4k', rating:'4.8' },
    { name:'vigil-ward-agent', type:'A2A Agent', author:'Vigil Health',
      desc:'Autonomous post-op/postpartum monitor. Deterministic 7-state machine. HITL by default.',
      installs:'810', rating:'4.9' },
  ];
  return (
    <div className="page">
      <div className="page__hd">
        <h1 className="page__title">Prompt Opinion Marketplace</h1>
        <span className="page__sub">2 listings · published · verified</span>
      </div>
      <div className="alerts-list">
        {listings.map(l => (
          <div key={l.name} className="alert-card" style={{gridTemplateColumns:'auto 1fr auto'}}>
            <div style={{width:40, height:40, borderRadius:6, background:'var(--ink-700)', color:'#fff', display:'flex', alignItems:'center', justifyContent:'center', fontFamily:'var(--font-mono)', fontWeight:600, fontSize:14}}>
              {l.type[0]}
            </div>
            <div>
              <div className="who">{l.name}<span className="bed">· {l.type} · {l.author}</span></div>
              <div className="msg">{l.desc}</div>
            </div>
            <div className="meta">
              {l.installs} installs<br/>
              <span style={{color:'var(--warning)'}}>★ {l.rating}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { App, Marketplace });

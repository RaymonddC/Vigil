// SBAR card + Vitals chart + Approve bar components

function SBARCard({ patient, approved, approver }) {
  const s = patient.sbar || {
    situation: '—', background: '—', assessment: '—', recommend: '—'
  };
  return (
    <div className="sbar">
      <div className="sbar__hd">
        <span className="sbar__tag">{approved ? 'SBAR · APPROVED' : 'SBAR · DRAFT'}</span>
        <span className="sbar__title">{patient.bed} · {patient.name}</span>
        <span className="sbar__time">14:02</span>
      </div>
      <div className="sbar__sec"><span className="sbar__k">Situation</span>   <span className="sbar__v">{s.situation}</span></div>
      <div className="sbar__sec"><span className="sbar__k">Background</span>  <span className="sbar__v">{s.background}</span></div>
      <div className="sbar__sec"><span className="sbar__k">Assessment</span>  <span className="sbar__v">{s.assessment}</span></div>
      <div className="sbar__sec"><span className="sbar__k">Recommend</span>   <span className="sbar__v">{s.recommend}</span></div>
    </div>
  );
}

function ApproveBar({ onApprove, onDismiss, approved, approver }) {
  if (approved) {
    return (
      <div className="attr-toast" role="status">
        <span className="av">{approver.initials}</span>
        <span className="txt">Approved by {approver.full} · written to EHR</span>
        <span className="time">14:07</span>
      </div>
    );
  }
  return (
    <div className="approve-bar">
      <Button onClick={onDismiss}>Dismiss</Button>
      <span className="grow"></span>
      <Button variant="ghost" size="sm">Edit draft</Button>
      <Button variant="primary" size="lg" onClick={onApprove}>Approve handoff →</Button>
    </div>
  );
}

function VitalsChart({ patient }) {
  // synthesize 24h of data deterministically from patient.id
  const seed = patient.id.charCodeAt(patient.id.length-1);
  const N = 48;
  const hr = [], map = [], spo2 = [];
  for (let i=0;i<N;i++){
    const t = i/(N-1);
    const trend = patient.risk==='critical' ? Math.pow(t, 1.6) : patient.risk==='high' ? t*0.7 : 0;
    const noise = Math.sin(i*0.9 + seed)*0.5 + Math.cos(i*0.45)*0.3;
    hr.push  (80 + trend*55 + noise*3);
    map.push (88 - trend*28 + noise*2);
    spo2.push(98 - trend*4  + noise*0.5);
  }
  const W = 720, H = 200, PAD_L = 36, PAD_R = 10, PAD_T = 14, PAD_B = 24;
  const IW = W-PAD_L-PAD_R, IH = H-PAD_T-PAD_B;
  function scale(arr, min, max) {
    return arr.map((v,i) => [PAD_L + (i/(N-1))*IW, PAD_T + (1-(v-min)/(max-min))*IH]);
  }
  const hrPts   = scale(hr,   50, 160);
  const mapPts  = scale(map,  40, 100);
  const spo2Pts = scale(spo2, 85, 100);
  const path = pts => 'M' + pts.map(p=>`${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' L');
  const flagIdx = Math.floor(N*0.75);
  return (
    <div className="panel">
      <div className="panel__hd">
        <span className="t">Vitals · 24 hours</span>
        <span className="s">updated 14:02</span>
        <span style={{marginLeft:'auto', display:'flex', gap:14, fontFamily:'var(--font-mono)', fontSize:10, color:'var(--fg-3)'}}>
          <span><span style={{display:'inline-block',width:10,height:2,background:'var(--risk-critical)',marginRight:4,verticalAlign:'middle'}}></span>HR</span>
          <span><span style={{display:'inline-block',width:10,height:2,background:'var(--ink-700)',marginRight:4,verticalAlign:'middle'}}></span>MAP</span>
          <span><span style={{display:'inline-block',width:10,height:2,background:'var(--success)',marginRight:4,verticalAlign:'middle'}}></span>SpO₂</span>
        </span>
      </div>
      <div className="panel__body" style={{padding:'10px 14px 4px'}}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{width:'100%', height:200, display:'block'}}>
          {/* y gridlines */}
          <g stroke="var(--border-subtle)" strokeWidth="1">
            {[0.0, 0.25, 0.5, 0.75, 1.0].map((f,i)=>
              <line key={i} x1={PAD_L} x2={W-PAD_R} y1={PAD_T+f*IH} y2={PAD_T+f*IH}/>
            )}
          </g>
          {/* y labels */}
          <g fill="var(--fg-3)" fontFamily="var(--font-mono)" fontSize="10">
            <text x="4" y={PAD_T+4}>160</text>
            <text x="4" y={PAD_T+IH/2+4}>105</text>
            <text x="4" y={PAD_T+IH+4}>50</text>
          </g>
          {/* flag marker */}
          {patient.risk==='critical' && (
            <line
              x1={PAD_L+(flagIdx/(N-1))*IW} x2={PAD_L+(flagIdx/(N-1))*IW}
              y1={PAD_T} y2={PAD_T+IH}
              stroke="var(--risk-critical)" strokeWidth="1" strokeDasharray="2 3"
            />
          )}
          <path d={path(hrPts)}   stroke="var(--risk-critical)" strokeWidth="1.5" fill="none"/>
          <path d={path(mapPts)}  stroke="var(--ink-700)"       strokeWidth="1.5" fill="none"/>
          <path d={path(spo2Pts)} stroke="var(--success)"       strokeWidth="1.5" fill="none"/>
          {/* x labels */}
          <g fill="var(--fg-3)" fontFamily="var(--font-mono)" fontSize="10">
            {['−24h','−18','−12','−6','now'].map((t,i)=>
              <text key={i} x={PAD_L + (i/4)*IW} y={H-6} textAnchor={i===0?'start':i===4?'end':'middle'}>{t}</text>
            )}
          </g>
        </svg>
      </div>
      <div className="vital-grid">
        <VitalTile lbl="HR"    val={patient.vitals.hr}   unit="bpm"  alert={patient.vitals.hr>110}/>
        <VitalTile lbl="MAP"   val={patient.vitals.map}  unit="mmHg" alert={patient.vitals.map<65}/>
        <VitalTile lbl="SpO₂"  val={patient.vitals.spo2} unit="%"    alert={patient.vitals.spo2<95}/>
        <VitalTile lbl="Temp"  val={patient.vitals.temp} unit="°C"   alert={patient.vitals.temp>38}/>
      </div>
    </div>
  );
}
function VitalTile({ lbl, val, unit, alert }) {
  return (
    <div className={`vital${alert?' alert':''}`}>
      <div className="lbl">{lbl}</div>
      <div className="num">{val}<span className="unit"> {unit}</span></div>
      <div className="trend">{alert?'↑ out of range':'within range'}</div>
    </div>
  );
}

Object.assign(window, { SBARCard, ApproveBar, VitalsChart, VitalTile });

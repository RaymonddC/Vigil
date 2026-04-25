// Seed data for the prototype
const PATIENTS = [
  { id:'p12', bed:'B-12', name:'Martinez, A.',   mrn:'00428', ward:'POST-OP', admit:'2026-04-24', day:'POD 1', risk:'critical',
    vitals:{ hr:128, map:62, spo2:94, temp:38.4, rr:24 },
    alert:'Rising lactate · MAP trending', alertTime:'14:02',
    comorbid:['Type 2 diabetes','Hypertension'],
    reasoning:[
      'HR rose from 92 → 128 bpm over the last 3 hours',
      'MAP dropped below 65 mmHg at 13:40 and has not recovered',
      'Lactate 3.2 mmol/L at 13:55, up from 1.4 mmol/L this morning',
      'qSOFA 2, NEWS2 8 — meets early sepsis screen'
    ],
    sbar:{
      situation: 'Tachycardia and relative hypotension since 11:40, now with a rising serum lactate.',
      background: 'POD 1 bowel resection under GA. Epidural in place. T2DM, HTN. No prior sepsis.',
      assessment: 'Concern for early septic physiology. qSOFA 2, NEWS2 8. Not yet meeting full sepsis criteria.',
      recommend: 'Bedside evaluation within 15 minutes. Repeat lactate, blood cultures, broad-spectrum antibiotics per protocol, 500 mL crystalloid challenge.'
    }},
  { id:'p07', bed:'B-07', name:'Okafor, C.',     mrn:'00391', ward:'POSTPARTUM', admit:'2026-04-24', day:'PPD 1', risk:'high',
    vitals:{ hr:108, map:71, spo2:96, temp:37.8, rr:20 },
    alert:'Postpartum BP trend', alertTime:'13:48', comorbid:['Preeclampsia'],
    reasoning:['BP 158/102 on last reading','HR climbing 6h','Proteinuria 2+']},
  { id:'p14', bed:'B-14', name:'Abramov, N.',    mrn:'00462', ward:'POST-OP', admit:'2026-04-23', day:'POD 2', risk:'medium',
    vitals:{ hr:96, map:78, spo2:97, temp:37.4, rr:18 },
    alert:'Urine output borderline', alertTime:'13:12', comorbid:['CKD stage 2']},
  { id:'p03', bed:'B-03', name:'Singh, R.',      mrn:'00256', ward:'POST-OP', admit:'2026-04-23', day:'POD 2', risk:'normal',
    vitals:{ hr:82, map:86, spo2:98, temp:36.9, rr:14 }, alert:'—', alertTime:'—', comorbid:[]},
  { id:'p05', bed:'B-05', name:'Johansson, E.',  mrn:'00302', ward:'POSTPARTUM', admit:'2026-04-24', day:'PPD 0', risk:'low',
    vitals:{ hr:88, map:82, spo2:98, temp:37.1, rr:16 }, alert:'—', alertTime:'—', comorbid:[]},
  { id:'p09', bed:'B-09', name:'Garcia, L.',     mrn:'00357', ward:'POST-OP', admit:'2026-04-22', day:'POD 3', risk:'normal',
    vitals:{ hr:76, map:90, spo2:99, temp:36.8, rr:14 }, alert:'—', alertTime:'—', comorbid:['Asthma']},
  { id:'p11', bed:'B-11', name:'Tanaka, H.',     mrn:'00411', ward:'POST-OP', admit:'2026-04-23', day:'POD 2', risk:'low',
    vitals:{ hr:84, map:84, spo2:97, temp:37.0, rr:15 }, alert:'—', alertTime:'—', comorbid:[]},
  { id:'p06', bed:'B-06', name:'Dubois, M.',     mrn:'00339', ward:'POSTPARTUM', admit:'2026-04-24', day:'PPD 1', risk:'normal',
    vitals:{ hr:80, map:85, spo2:98, temp:37.0, rr:15 }, alert:'—', alertTime:'—', comorbid:[]},
];

const AGENT_STATES = [
  { state:'IDLE',          desc:'waiting for next poll'           },
  { state:'POLLING',       desc:'fetching FHIR vitals'            },
  { state:'SCREENING',     desc:'applying NEWS2 thresholds'       },
  { state:'RISK_SCORING',  desc:'computing composite score'       },
  { state:'SEPSIS_CHECK',  desc:'evaluating lactate + MAP trend'  },
  { state:'ESCALATING',    desc:'drafting SBAR'                   },
  { state:'AWAITING_REVIEW', desc:'human-in-the-loop'             },
];

const SEED_TRACE = [
  { t:'14:01:58', state:'POLLING',      detail:'fetched FHIR vitals for 8 beds', ms:220, done:true },
  { t:'14:02:01', state:'SCREENING',    detail:'flagged Bed 12 for review',      ms:180, done:true },
  { t:'14:02:03', state:'RISK_SCORING', detail:'NEWS2 = 8 · qSOFA = 2',          ms:412, done:true },
  { t:'14:02:04', state:'SEPSIS_CHECK', detail:'lactate trend 1.4 → 3.2 mmol/L', ms:688, done:true },
  { t:'14:02:05', state:'ESCALATING',   detail:'drafting SBAR for Dr. Patel',    ms:null, done:false, active:true },
];

Object.assign(window, { PATIENTS, AGENT_STATES, SEED_TRACE });

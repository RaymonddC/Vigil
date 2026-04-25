// Shared atoms for Vigil app kit. Exports to window.

const CLINICIANS = [
  { id: 'sc', name: 'Sarah Chen',       initials: 'SC', role: 'RN',        full: 'Sarah Chen, RN' },
  { id: 'ml', name: 'Maya Lee',         initials: 'ML', role: 'CHARGE',    full: 'Maya Lee, Charge Nurse' },
  { id: 'ap', name: 'Dr. Amit Patel',   initials: 'AP', role: 'ICU',       full: 'Dr. Amit Patel, Intensivist' },
  { id: 'lp', name: 'Dr. Lindsay Park', initials: 'LP', role: 'RAPID',     full: 'Dr. Lindsay Park, Rapid Response' },
];

const RISK_GLYPH = { normal:'○', low:'◔', medium:'◐', high:'◕', critical:'●' };
const RISK_LABEL = { normal:'Normal', low:'Low', medium:'Medium', high:'High', critical:'Critical' };

function RiskChip({ level }) {
  return (
    <span className={`rchip rchip--${level}`} role="status" aria-label={`Risk ${RISK_LABEL[level]}`}>
      <span className="g" aria-hidden="true">{RISK_GLYPH[level]}</span>
      {RISK_LABEL[level]}
    </span>
  );
}

function RiskStripe({ level }) {
  const color = {
    normal: 'var(--risk-normal)', low: 'var(--risk-low)',
    medium: 'var(--risk-medium)', high: 'var(--risk-high)',
    critical: 'var(--risk-critical)'
  }[level];
  return <div className="roster__stripe" style={{ background: color }} aria-hidden="true"></div>;
}

function Button({ variant = 'default', size, children, onClick, disabled, ...rest }) {
  const cls = ['btn'];
  if (variant === 'primary') cls.push('btn--primary');
  if (variant === 'danger')  cls.push('btn--danger');
  if (variant === 'ghost')   cls.push('btn--ghost');
  if (size === 'lg')         cls.push('btn--lg');
  if (size === 'sm')         cls.push('btn--sm');
  return <button className={cls.join(' ')} onClick={onClick} disabled={disabled} {...rest}>{children}</button>;
}

function Panel({ title, meta, right, children, style }) {
  return (
    <div className="panel" style={style}>
      {(title || right) && (
        <div className="panel__hd">
          {title && <span className="t">{title}</span>}
          {meta && <span className="s">{meta}</span>}
          {right && <span style={{ marginLeft: 'auto' }}>{right}</span>}
        </div>
      )}
      {children}
    </div>
  );
}

function Icon({ name, size = 16 }) {
  // Render an <i data-lucide> and have Lucide swap it in after mount
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (window.lucide && ref.current) {
      ref.current.innerHTML = `<i data-lucide="${name}" style="width:${size}px;height:${size}px;stroke-width:1.75;"></i>`;
      window.lucide.createIcons({ attrs: { width: size, height: size } });
    }
  }, [name, size]);
  return <span ref={ref} style={{ display: 'inline-flex', width: size, height: size }} aria-hidden="true"></span>;
}

Object.assign(window, { CLINICIANS, RISK_GLYPH, RISK_LABEL, RiskChip, RiskStripe, Button, Panel, Icon });

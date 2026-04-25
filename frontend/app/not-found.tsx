import Link from "next/link";

export default function NotFound() {
  return (
    <div className="page">
      <div className="page__hd">
        <h1 className="page__title">Page not found</h1>
        <span className="page__sub">404</span>
      </div>
      <div className="empty" style={{ paddingBottom: 24 }}>
        <p style={{ marginBottom: 14 }}>
          The page you are looking for does not exist or has been moved.
        </p>
        <Link href="/patients" className="btn btn--primary">
          Back to roster
        </Link>
      </div>
    </div>
  );
}

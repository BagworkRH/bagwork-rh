import Link from "next/link";

export default function NotFound() {
  return (
    <div className="container section">
      <div className="card" style={{ textAlign: "center", padding: 40 }}>
        <h1>404 — Page not found</h1>
        <p className="muted">The page you&apos;re looking for doesn&apos;t exist.</p>
        <Link href="/" className="btn btn-primary">
          Back home
        </Link>
      </div>
    </div>
  );
}
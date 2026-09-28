import Link from "next/link";
import BrandLogo from "@/lib/brand";

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="container footer-grid">
        <div>
          <p className="brand">
            <BrandLogo size={26} />
          </p>
          <p className="muted">
            Earn crypto rewards for verified social promotion.
          </p>
        </div>
        <div>
          <h4>Platform</h4>
          <ul>
            <li><Link href="/campaigns">Campaigns</Link></li>
            <li><Link href="/how-it-works">How It Works</Link></li>
            <li><Link href="/dashboard">Dashboard</Link></li>
          </ul>
        </div>
        <div>
          <h4>Legal</h4>
          <ul>
            <li><Link href="/help#terms">Terms of Service</Link></li>
            <li><Link href="/help#privacy">Privacy Policy</Link></li>
            <li><Link href="/help#disclosure">Paid Partnership Disclosure</Link></li>
          </ul>
        </div>
        <div>
          <h4>Support</h4>
          <ul>
            <li><Link href="/help">Help Center</Link></li>
            <li><Link href="/help#report">Report</Link></li>
          </ul>
        </div>
      </div>
      <p className="container footer-legal muted">
        © {new Date().getFullYear()} bagworkRH. Cryptocurrency rewards carry
        risk; nothing here is financial advice.
      </p>
    </footer>
  );
}
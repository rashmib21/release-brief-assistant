import { useQuery } from "@tanstack/react-query";
import { Link, Route, Routes } from "react-router-dom";

import { api } from "./api";

import BriefPage from "./pages/BriefPage";
import ComparePage from "./pages/ComparePage";
import PackageFormPage from "./pages/PackageFormPage";
import ReleasePage from "./pages/ReleasePage";
import ReleasesPage from "./pages/ReleasesPage";
import ReviewPage from "./pages/ReviewPage";
import { Empty } from "./ui";

function BrandMark() {
  // A page with a check: drafted, then reviewed.
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect x="5" y="3" width="22" height="26" rx="3" fill="none" stroke="currentColor" strokeWidth="2.2" />
      <path d="M10 10h12M10 15h8" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M11 22.5l3.2 3.2L22 18.5" fill="none" stroke="#ffe58a" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export const UI_BUILD = "2026-10-16b";

/** Shows which UI and API versions are running. If the API build is missing, the old server is still running. */
function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: () => api<{ build?: string; llm_provider: string }>("/health"), retry: false });
}

function OldServerBanner() {
  const health = useHealth();
  if (!health.data || health.data.build) return null;
  return (
    <div className="alert alert-error" role="alert">
      <div>
        <strong>An old server is still running.</strong> This page is new, but the API behind it is an old version, so errors will continue. Close every terminal running the server (or the python process using port 8000), then start it again with start.bat or start.sh.
      </div>
    </div>
  );
}

function Footer() {
  const health = useHealth();
  const apiBuild = health.isError ? "not reachable" : health.data ? (health.data.build ?? "OLD, restart the server") : "…";
  return (
    <footer className="app-footer">
      UI build {UI_BUILD} · API build {apiBuild}
      {health.data && ` · AI: ${health.data.llm_provider}`}
    </footer>
  );
}

export default function App() {
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand">
            <BrandMark />
            Release Brief Assistant
          </Link>
          <span className="tagline">The AI drafts. You approve. Nothing here deploys or approves a release.</span>
        </div>
      </header>
      <main className="container">
        <OldServerBanner />
        <Routes>
          <Route path="/" element={<ReleasesPage />} />
          <Route path="/releases/:rid" element={<ReleasePage />} />
          <Route path="/releases/:rid/versions/new" element={<PackageFormPage mode="new" />} />
          <Route path="/releases/:rid/compare" element={<ComparePage />} />
          <Route path="/versions/:vid" element={<ReviewPage />} />
          <Route path="/versions/:vid/edit" element={<PackageFormPage mode="edit" />} />
          <Route path="/versions/:vid/brief" element={<BriefPage />} />
          <Route
            path="*"
            element={
              <Empty title="This page does not exist">
                <Link to="/">Go to your releases</Link>
              </Empty>
            }
          />
        </Routes>
      </main>
      <Footer />
    </>
  );
}

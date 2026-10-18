import { lazy, Suspense, useState } from "react";
import {
  HashRouter,
  Link,
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { getToken, clearSession, getUser } from "./api";
import { applyTheme, currentTheme, type Theme } from "./theme";
import LoginPage from "./pages/LoginPage";

// Route-level code splitting: heavy vendor libraries (Plotly ~3.5 MB,
// React Flow) live inside these page modules and are only fetched when the
// route is first opened. vite.config.ts additionally emits them as their own
// cacheable chunks via manualChunks.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Workspace = lazy(() => import("./pages/Workspace"));
const Coordination = lazy(() => import("./pages/Coordination"));
const ContextGraphPage = lazy(() => import("./pages/ContextGraph"));
const MemoryExplorer = lazy(() => import("./pages/MemoryExplorer"));
const StellarLab = lazy(() => import("./pages/StellarLab"));
const CelestialGallery = lazy(() => import("./pages/CelestialGallery"));
const CelestialSim = lazy(() => import("./pages/CelestialSim"));
const CosmologyLab = lazy(() => import("./pages/CosmologyLab"));
const ObservationExplorer = lazy(() => import("./pages/ObservationExplorer"));
const ReportCenter = lazy(() => import("./pages/ReportCenter"));
const PaperLab = lazy(() => import("./pages/PaperLab"));
const Explainer = lazy(() => import("./pages/Explainer"));

// Shared glossary dialog: mounted once in the shell so any ExplainText click
// (labs, workspace, paper findings) opens the same overlay.
import { ExplainDialog } from "./components/Explain";

// ---------------------------------------------------------------------------
// Nested navigation: two sections, each with an index page and child pages.
// ---------------------------------------------------------------------------

interface NavItem {
  to: string;
  label: string;
  note: string;
}

const SECTIONS: Array<{ path: string; label: string; blurb: string; items: NavItem[] }> = [
  {
    path: "research",
    label: "Research",
    blurb:
      "Run autonomous investigations, watch agents coordinate, and explore the " +
      "scientific memory they build across sessions.",
    items: [
      { to: "/research/workspace", label: "Research Workspace", note: "Converse with the orchestrator and run investigations" },
      { to: "/research/paper", label: "Paper → Simulation", note: "Paste a paper link; agents extract claims, run engines, explain" },
      { to: "/research/coordination", label: "Agent Coordination", note: "Live dependency graph with per-node evidence" },
      { to: "/research/context", label: "Context Graph", note: "FalkorDB property graph of questions, runs and findings" },
      { to: "/research/memory", label: "Memory Explorer", note: "Episodic, semantic and procedural memory" },
      { to: "/explainer", label: "Explainer", note: "Plain-language glossary behind every term and finding" },
    ],
  },
  {
    path: "labs",
    label: "Labs",
    blurb:
      "Five laboratories and data galleries. Every number and image on these " +
      "pages originates from an executed tool run — never from prose.",
    items: [
      { to: "/labs/celestial", label: "Celestial Simulator", note: "REBOUND N-body integrations with conservation diagnostics" },
      { to: "/labs/stellar", label: "Stellar Lab", note: "Main-sequence models against published reference stars" },
      { to: "/labs/cosmology", label: "Cosmology Lab", note: "ΛCDM distance ladder, expansion history, MCMC posteriors" },
      { to: "/labs/observations", label: "Observation Explorer", note: "FITS, archives, cross-matching, light curves" },
      { to: "/labs/gallery", label: "Celestial Gallery", note: "Real captured imagery — NASA Picture of the Day, full resolution" },
    ],
  },
];

function RouteFallback() {
  return (
    <div className="flex h-64 items-center justify-center text-sm uppercase tracking-[0.18em] text-slate-400">
      Loading
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shell: fixed top bar + full-screen overlay menu (Atlason-style).
// ---------------------------------------------------------------------------

function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className="text-[12px] font-medium uppercase tracking-[0.14em] hover:underline underline-offset-4"
      title="Switch between dark and light theme"
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
    >
      {theme === "dark" ? "Light" : "Dark"}
    </button>
  );
}

function TopBar({ onOpenMenu, theme, onToggleTheme }: {
  onOpenMenu: () => void;
  theme: Theme;
  onToggleTheme: () => void;
}) {
  return (
    <header className="sticky top-0 z-40 flex items-center justify-between border-b border-slate-700 bg-slate-950 px-6 py-4">
      <Link to="/" className="font-disp text-lg font-medium tracking-[-0.01em]">
        NOESIS
      </Link>
      <div className="flex items-center gap-6">
        <nav className="hidden items-center gap-5 text-[12px] uppercase tracking-[0.14em] md:flex">
          {SECTIONS.map((s) => (
            <NavLink
              key={s.path}
              to={`/${s.path}`}
              className={({ isActive }) =>
                isActive ? "underline decoration-2 underline-offset-4" : "hover:underline underline-offset-4"
              }
            >
              {s.label}
            </NavLink>
          ))}
          <NavLink
            to="/reports"
            className={({ isActive }) =>
              isActive ? "underline decoration-2 underline-offset-4" : "hover:underline underline-offset-4"
            }
          >
            Reports
          </NavLink>
          <NavLink
            to="/explainer"
            className={({ isActive }) =>
              isActive ? "underline decoration-2 underline-offset-4" : "hover:underline underline-offset-4"
            }
          >
            Explainer
          </NavLink>
        </nav>
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        <button
          onClick={onOpenMenu}
          className="text-[12px] font-medium uppercase tracking-[0.14em] hover:underline underline-offset-4"
        >
          Menu
        </button>
      </div>
    </header>
  );
}

function OverlayMenu({ open, onClose, theme, onToggleTheme }: {
  open: boolean;
  onClose: () => void;
  theme: Theme;
  onToggleTheme: () => void;
}) {
  const user = getUser();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-950">
      <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
        <Link to="/" onClick={onClose} className="font-disp text-lg font-medium">
          NOESIS
        </Link>
        <div className="flex items-center gap-6">
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
          <button
            onClick={onClose}
            className="text-[12px] font-medium uppercase tracking-[0.14em] hover:underline underline-offset-4"
          >
            Close
          </button>
        </div>
      </div>

      <div className="px-6 py-10 md:px-10">
        <Link
          to="/"
          onClick={onClose}
          className="display block hover:opacity-60"
        >
          Dashboard
        </Link>

        {SECTIONS.map((section) => (
          <div key={section.path} className="mt-10 border-t border-slate-700 pt-8">
            <Link
              to={`/${section.path}`}
              onClick={onClose}
              className="display block hover:opacity-60"
            >
              {section.label}
            </Link>
            <ul className="mt-5 grid gap-x-10 gap-y-3 md:grid-cols-2">
              {section.items.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    onClick={onClose}
                    className="group flex items-baseline justify-between gap-4 border-b border-slate-800 pb-2"
                  >
                    <span className="text-[15px] group-hover:underline underline-offset-4">
                      {item.label}
                    </span>
                    <span className="hidden text-[11px] uppercase tracking-[0.12em] text-slate-400 md:block">
                      {item.note}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}

        <div className="mt-10 grid gap-x-10 gap-y-3 border-t border-slate-700 pt-8 md:grid-cols-2">
          <Link to="/reports" onClick={onClose} className="display block hover:opacity-60">
            Reports
          </Link>
          <Link to="/explainer" onClick={onClose} className="display block hover:opacity-60">
            Explainer
          </Link>
        </div>

        {/* Footer meta columns, Atlason "Visit / Connect / Follow" style */}
        <div className="mt-16 grid gap-8 border-t border-slate-700 pt-8 text-[13px] md:grid-cols-3">
          <div>
            <div className="eyebrow mb-2">Platform</div>
            <p className="text-slate-300">
              Autonomous multi-agent astrophysics research. Every figure originates
              from an executed tool run. 11 specialized agents.
            </p>
          </div>
          <div>
            <div className="eyebrow mb-2">Account</div>
            {user ? (
              <>
                <div>{user.email}</div>
                <div className="text-slate-400">tenant {user.tenant_id.slice(0, 8)}…</div>
                <button                   className="mt-2 border-b border-slate-100 text-[12px] uppercase tracking-[0.14em] hover:opacity-60"
                  onClick={() => {
                    clearSession();
                    window.location.hash = "#/login";
                  }}
                >
                  Sign out
                </button>
              </>
            ) : (
              <Link to="/login" className="border-b border-slate-100 hover:opacity-60">
                Sign in
              </Link>
            )}
          </div>
          <div>
            <div className="eyebrow mb-2">Stack</div>
            <p className="text-slate-300">
              FastAPI · LangGraph-style orchestration · PostgreSQL + pgvector ·
              FalkorDB context graph · REBOUND · Astropy · emcee
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Shell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>(() => currentTheme());
  const location = useLocation();
  const toggleTheme = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  };
  return (
    <div className="min-h-screen bg-slate-950">
      <TopBar onOpenMenu={() => setMenuOpen(true)} theme={theme} onToggleTheme={toggleTheme} />
      <OverlayMenu open={menuOpen} onClose={() => setMenuOpen(false)}
                   theme={theme} onToggleTheme={toggleTheme} />
      {/* Remount on route change only (clean lazy-route state). Theme
          toggles repaint in place: pages and charts subscribe via useTheme(),
          so page state (inputs, loaded data, open views) survives a toggle. */}
      <main key={location.pathname} className="px-6 py-10 md:px-10">
        <Suspense fallback={<RouteFallback />}>
          <Outlet />
        </Suspense>
      </main>
      <ExplainDialog />
    </div>
  );
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return children;
}

// ---------------------------------------------------------------------------
// Section index pages (nested landing pages, Atlason "Works" style)
// ---------------------------------------------------------------------------

function SectionIndex({ path }: { path: string }) {
  const section = SECTIONS.find((s) => s.path === path)!;
  return (
    <div>
      <div className="eyebrow">Section</div>
      <h1 className="display mt-3">{section.label}</h1>
      <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-slate-300">
        {section.blurb}
      </p>
      <ul className="mt-12 border-t border-slate-700">
        {section.items.map((item, i) => (
          <li key={item.to} className="border-b border-slate-700">
            <Link
              to={item.to}
              className="group flex flex-wrap items-baseline justify-between gap-x-8 gap-y-1 py-6"
            >
              <span className="display-sm group-hover:underline decoration-2 underline-offset-[6px]">
                <span className="mr-4 text-slate-500">{String(i + 1).padStart(2, "0")}</span>
                {item.label}
              </span>
              <span className="text-[13px] text-slate-400">{item.note}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<RequireAuth><Shell /></RequireAuth>}>
          <Route index element={<Dashboard />} />
          <Route path="reports" element={<ReportCenter />} />
          <Route path="explainer" element={<Explainer />} />

          {/* Nested research section */}
          <Route path="research">
            <Route index element={<SectionIndex path="research" />} />
            <Route path="workspace" element={<Workspace />} />
            <Route path="workspace/:sessionId" element={<Workspace />} />
            <Route path="paper" element={<PaperLab />} />
            <Route path="coordination" element={<Coordination />} />
            <Route path="coordination/:sessionId" element={<Coordination />} />
            <Route path="context" element={<ContextGraphPage />} />
            <Route path="memory" element={<MemoryExplorer />} />
          </Route>

          {/* Nested labs section */}
          <Route path="labs">
            <Route index element={<SectionIndex path="labs" />} />
            <Route path="stellar" element={<StellarLab />} />
            <Route path="celestial" element={<CelestialSim />} />
            <Route path="cosmology" element={<CosmologyLab />} />
            <Route path="observations" element={<ObservationExplorer />} />
            <Route path="gallery" element={<CelestialGallery />} />
          </Route>

          {/* Legacy flat routes -> nested equivalents */}
          <Route path="memory" element={<Navigate to="/research/memory" replace />} />
          <Route path="context" element={<Navigate to="/research/context" replace />} />
          <Route path="workspace" element={<Navigate to="/research/workspace" replace />} />
          <Route path="paper" element={<Navigate to="/research/paper" replace />} />
          <Route path="coordination" element={<Navigate to="/research/coordination" replace />} />
          <Route path="stellar" element={<Navigate to="/labs/stellar" replace />} />
          <Route path="celestial" element={<Navigate to="/labs/celestial" replace />} />
          <Route path="cosmology" element={<Navigate to="/labs/cosmology" replace />} />
          <Route path="observations" element={<Navigate to="/labs/observations" replace />} />
          <Route path="gallery" element={<Navigate to="/labs/gallery" replace />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}

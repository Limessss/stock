import { useEffect, useMemo, useState, type ComponentType } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { LucideProps } from "lucide-react";
import { Activity, ChevronDown, ChevronLeft, ChevronRight, Moon, PanelLeftClose, PanelLeftOpen, Sun } from "lucide-react";

import {
  AppstoreOutlined, BookOutlined, DashboardOutlined, ExperimentOutlined, FireOutlined,
  LineChartOutlined, RiseOutlined, RobotOutlined,
  SettingOutlined,
} from "@/components/ui/icons";
import { syncMarketToday } from "@/api/market";
import { useThemeStore } from "@/store/theme";

import BacktestPage from "@/pages/Backtest";
import DataManagePage from "@/pages/DataManage";
import GannAnalysisPage from "@/pages/GannAnalysis";
import HealthPage from "@/pages/Health";
import IntervalGainsPage from "@/pages/IntervalGains";
import LeaderCyclePanoramaPage from "@/pages/LeaderCyclePanorama";
import ReviewNoteEditorPage from "@/pages/ReviewNoteEditor";
import ReviewNotesPage from "@/pages/ReviewNotes";
import ScanPage from "@/pages/Scan";
import SentimentCyclePage from "@/pages/SentimentCycle";
import StrategiesPage from "@/pages/Strategies";
import StrategyDetailPage from "@/pages/StrategyDetail";
import SettingsLayout, { SettingsIndexRedirect } from "@/pages/settings/SettingsLayout";
import LlmProviderSettings from "@/pages/settings/LlmProviderSettings";

type Icon = ComponentType<LucideProps>;
type NavItem = { path: string; label: string; caption: string; icon: Icon };

const primaryNav: NavItem[] = [
  { path: "/", label: "市场总览", caption: "状态与数据", icon: DashboardOutlined },
  { path: "/scan", label: "选股扫描", caption: "策略筛选", icon: LineChartOutlined },
  { path: "/strategies", label: "策略模型", caption: "模型配置", icon: AppstoreOutlined },
  { path: "/backtest", label: "回测中心", caption: "验证与复盘", icon: ExperimentOutlined },
  { path: "/gann", label: "江恩角度线", caption: "趋势结构", icon: RiseOutlined },
  { path: "/notes", label: "复盘笔记", caption: "交易记录", icon: BookOutlined },
];

const sentimentNav: NavItem[] = [
  { path: "/sentiment/ladder", label: "连板梯队", caption: "情绪矩阵", icon: FireOutlined },
  { path: "/sentiment/interval-gains", label: "区间涨幅", caption: "涨幅排行", icon: RiseOutlined },
  { path: "/sentiment/leader-panorama", label: "龙头周期全景图", caption: "多图联动", icon: LineChartOutlined },
];

const settingNav: NavItem[] = [
  { path: "/settings/data", label: "数据管理", caption: "缓存与同步", icon: SettingOutlined },
  { path: "/settings/llm", label: "大模型设置", caption: "服务商配置", icon: RobotOutlined },
];

function matchPath(pathname: string, path: string) {
  if (path === "/") return pathname === "/";
  return pathname.startsWith(path);
}

function NavLink({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  const location = useLocation();
  const active = matchPath(location.pathname, item.path);
  const IconComponent = item.icon;
  return (
    <Link to={item.path} className={`shell-nav-item${active ? " is-active" : ""}`} title={collapsed ? item.label : undefined}>
      <span className="shell-nav-icon"><IconComponent size={17} /></span>
      {!collapsed && <span className="shell-nav-copy"><strong>{item.label}</strong><small>{item.caption}</small></span>}
      {!collapsed && active && <ChevronRight className="shell-nav-arrow" size={14} />}
    </Link>
  );
}

function ShellHeader({ collapsed, onToggleSidebar }: { collapsed: boolean; onToggleSidebar: () => void }) {
  const location = useLocation();
  const themeMode = useThemeStore((s) => s.mode);
  const toggleTheme = useThemeStore((s) => s.toggle);
  const current = [...primaryNav, ...sentimentNav, ...settingNav].find((item) => matchPath(location.pathname, item.path));
  return (
    <header className="shell-header">
      <div className="shell-header-left">
        <button className="shell-icon-button" onClick={onToggleSidebar} aria-label={collapsed ? "展开侧栏" : "收起侧栏"}>
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
        <span className="shell-header-divider" />
        <div className="shell-page-title"><span>A股研究台</span><ChevronRight size={13} /><strong>{current?.label ?? "工作台"}</strong></div>
      </div>
      <div className="shell-header-right">
        <div className="shell-market-status"><i /><span>数据服务正常</span></div>
        <button className="shell-icon-button" onClick={toggleTheme} aria-label="切换主题">{themeMode === "dark" ? <Sun size={17} /> : <Moon size={17} />}</button>
        <div className="shell-edition">LOCAL</div>
      </div>
    </header>
  );
}

export default function App() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const sentimentActive = location.pathname.startsWith("/sentiment");
  const settingsActive = location.pathname.startsWith("/settings");
  const [sentimentOpen, setSentimentOpen] = useState(sentimentActive);
  const [settingsOpen, setSettingsOpen] = useState(settingsActive);

  useEffect(() => { if (sentimentActive) setSentimentOpen(true); }, [sentimentActive]);
  useEffect(() => { if (settingsActive) setSettingsOpen(true); }, [settingsActive]);
  useEffect(() => {
    syncMarketToday().then(() => queryClient.invalidateQueries({ queryKey: ["market-overview"] })).catch(() => undefined);
  }, [queryClient]);

  const contentClass = useMemo(() => {
    if (location.pathname.startsWith("/notes")) return "page-container page-container--notes";
    if (location.pathname.startsWith("/sentiment")) return "page-container page-container--sentiment";
    return "page-container";
  }, [location.pathname]);

  return (
    <div className={`app-shell${collapsed ? " is-collapsed" : ""}`}>
      <aside className="shell-sidebar">
        <Link to="/" className="shell-brand">
          <span className="shell-brand-mark"><Activity size={20} /></span>
          {!collapsed && <span><strong>A股研究台</strong><small>STOCK RESEARCH</small></span>}
        </Link>
        <nav className="shell-nav">
          {!collapsed && <div className="shell-nav-section-label">分析工作区</div>}
          {primaryNav.map((item) => <NavLink key={item.path} item={item} collapsed={collapsed} />)}
          <button
            className={`shell-nav-item shell-nav-group${sentimentActive ? " is-active" : ""}`}
            onClick={() => collapsed ? navigate("/sentiment/ladder") : setSentimentOpen((value) => !value)}
            title={collapsed ? "情绪周期" : undefined}
          >
            <span className="shell-nav-icon"><FireOutlined size={17} /></span>
            {!collapsed && <span className="shell-nav-copy"><strong>情绪周期</strong><small>题材与梯队</small></span>}
            {!collapsed && <ChevronDown className={`shell-nav-arrow${sentimentOpen ? " is-open" : ""}`} size={14} />}
          </button>
          {!collapsed && sentimentOpen && <div className="shell-subnav">{sentimentNav.map((item) => <NavLink key={item.path} item={item} collapsed={false} />)}</div>}
          <button className={`shell-nav-item shell-nav-group${settingsActive ? " is-active" : ""}`} onClick={() => setSettingsOpen((v) => !v)} title={collapsed ? "系统设置" : undefined}>
            <span className="shell-nav-icon"><SettingOutlined size={17} /></span>
            {!collapsed && <span className="shell-nav-copy"><strong>系统设置</strong><small>数据与服务</small></span>}
            {!collapsed && <ChevronDown className={`shell-nav-arrow${settingsOpen ? " is-open" : ""}`} size={14} />}
          </button>
          {!collapsed && settingsOpen && <div className="shell-subnav">{settingNav.map((item) => <NavLink key={item.path} item={item} collapsed={false} />)}</div>}
        </nav>
        <div className="shell-sidebar-footer">
          {!collapsed ? <div className="shell-sync-card"><div><span>数据缓存</span><i>READY</i></div><strong>本地优先 · 增量同步</strong><small>最近状态正常，外部接口按需访问</small></div> : <span className="shell-ready-dot" />}
          <button className="shell-collapse" onClick={() => setCollapsed((v) => !v)}>{collapsed ? <ChevronRight size={16} /> : <><ChevronLeft size={16} /><span>收起侧栏</span></>}</button>
        </div>
      </aside>
      <div className="shell-main">
        <ShellHeader collapsed={collapsed} onToggleSidebar={() => setCollapsed((v) => !v)} />
        <main className={contentClass}>
          <Routes>
            <Route path="/" element={<HealthPage />} />
            <Route path="/scan" element={<ScanPage />} />
            <Route path="/strategies" element={<StrategiesPage />} />
            <Route path="/strategies/:name" element={<StrategyDetailPage />} />
            <Route path="/backtest" element={<BacktestPage />} />
            <Route path="/gann" element={<GannAnalysisPage />} />
            <Route path="/notes" element={<ReviewNotesPage />} />
            <Route path="/notes/:id" element={<ReviewNoteEditorPage />} />
            <Route path="/sentiment" element={<Navigate to="/sentiment/ladder" replace />} />
            <Route path="/sentiment/ladder" element={<SentimentCyclePage />} />
            <Route path="/sentiment/interval-gains" element={<IntervalGainsPage />} />
            <Route path="/sentiment/leader-panorama" element={<LeaderCyclePanoramaPage />} />
            <Route path="/data" element={<Navigate to="/settings/data" replace />} />
            <Route path="/settings" element={<SettingsLayout />}>
              <Route index element={<SettingsIndexRedirect />} />
              <Route path="data" element={<DataManagePage />} />
              <Route path="llm" element={<LlmProviderSettings />} />
            </Route>
          </Routes>
        </main>
      </div>
    </div>
  );
}

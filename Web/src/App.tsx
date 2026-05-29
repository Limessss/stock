import { useEffect, useMemo, useState } from "react";

import { Layout, Menu, Space, Switch, Typography, theme } from "antd";

import {

  DashboardOutlined,

  LineChartOutlined,

  ExperimentOutlined,

  MedicineBoxOutlined,

  FundOutlined,

  SwapOutlined,

  AppstoreOutlined,

  SettingOutlined,

  RobotOutlined,

  BulbOutlined,

  BulbFilled,

} from "@ant-design/icons";

import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";



import { useThemeStore } from "@/store/theme";



import HealthPage from "@/pages/Health";

import ScanPage from "@/pages/Scan";

import BacktestPage from "@/pages/Backtest";

import DiagnosePage from "@/pages/Diagnose";

import FactorPage from "@/pages/Factor";

import ComparePage from "@/pages/Compare";

import DataManagePage from "@/pages/DataManage";

import StrategiesPage from "@/pages/Strategies";

import StrategyDetailPage from "@/pages/StrategyDetail";

import TuningPage from "@/pages/Tuning";

import SettingsLayout, { SettingsIndexRedirect } from "@/pages/settings/SettingsLayout";

import LlmProviderSettings from "@/pages/settings/LlmProviderSettings";



const { Header, Sider, Content } = Layout;

const { Title } = Typography;



const menuItems = [

  { key: "/", label: <Link to="/">仪表盘</Link>, icon: <DashboardOutlined /> },

  { key: "/scan", label: <Link to="/scan">选股扫描</Link>, icon: <LineChartOutlined /> },

  { key: "/strategies", label: <Link to="/strategies">策略模型</Link>, icon: <AppstoreOutlined /> },

  { key: "/backtest", label: <Link to="/backtest">回测</Link>, icon: <ExperimentOutlined /> },

  { key: "/tuning", label: <Link to="/tuning">AI 调参</Link>, icon: <RobotOutlined /> },

  { key: "/diagnose", label: <Link to="/diagnose">个股诊断</Link>, icon: <MedicineBoxOutlined /> },

  { key: "/factor", label: <Link to="/factor">多因子分析</Link>, icon: <FundOutlined /> },

  { key: "/compare", label: <Link to="/compare">参数对比</Link>, icon: <SwapOutlined /> },

  {

    key: "settings",

    label: "系统设置",

    icon: <SettingOutlined />,

    children: [

      { key: "/settings/data", label: <Link to="/settings/data">数据管理</Link> },

      { key: "/settings/llm", label: <Link to="/settings/llm">大模型提供商</Link> },

    ],

  },

];



export default function App() {

  const [collapsed, setCollapsed] = useState(false);

  const location = useLocation();

  const {

    token: { colorBgContainer },

  } = theme.useToken();

  const themeMode = useThemeStore((s) => s.mode);

  const toggleTheme = useThemeStore((s) => s.toggle);



  const [menuOpenKeys, setMenuOpenKeys] = useState<string[]>([]);

  useEffect(() => {
    if (location.pathname.startsWith("/settings")) {
      setMenuOpenKeys(["settings"]);
    }
  }, [location.pathname]);

  const selectedKeys = useMemo(() => {

    if (location.pathname.startsWith("/settings")) {

      const sub = menuItems

        .find((m) => m.key === "settings")

        ?.children?.find((c) => location.pathname.startsWith(c.key as string));

      return [sub?.key ?? "/settings/data"];

    }

    if (location.pathname.startsWith("/strategies")) {

      return ["/strategies"];

    }

    const match = menuItems.find(

      (m) => typeof m.key === "string" && m.key !== "/" && location.pathname.startsWith(m.key)

    );

    return [match ? (match.key as string) : "/"];

  }, [location.pathname]);



  return (

    <Layout className="app-shell">

      <Sider

        collapsible

        collapsed={collapsed}

        onCollapse={setCollapsed}

        theme={themeMode === "dark" ? "dark" : "light"}

        width={220}

      >

        <div style={{ padding: 16 }}>

          <Title level={5} style={{ margin: 0, whiteSpace: "nowrap" }}>

            {collapsed ? "A股" : "A 股回测平台"}

          </Title>

        </div>

        <Menu

          mode="inline"

          selectedKeys={selectedKeys}

          openKeys={menuOpenKeys}

          onOpenChange={setMenuOpenKeys}

          items={menuItems}

          theme={themeMode === "dark" ? "dark" : "light"}

        />

      </Sider>

      <Layout>

        <Header style={{ background: colorBgContainer, padding: "0 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>

          <Title level={4} style={{ margin: "16px 0" }}>

            股票形态识别 + 回测可视化（个人单机版）

          </Title>

          <Space>

            <Switch

              checked={themeMode === "dark"}

              onChange={toggleTheme}

              checkedChildren={<BulbFilled />}

              unCheckedChildren={<BulbOutlined />}

            />

          </Space>

        </Header>

        <Content className="page-container">

          <Routes>

            <Route path="/" element={<HealthPage />} />

            <Route path="/scan" element={<ScanPage />} />

            <Route path="/strategies" element={<StrategiesPage />} />

            <Route path="/strategies/:name" element={<StrategyDetailPage />} />

            <Route path="/backtest" element={<BacktestPage />} />

            <Route path="/tuning" element={<TuningPage />} />

            <Route path="/diagnose" element={<DiagnosePage />} />

            <Route path="/factor" element={<FactorPage />} />

            <Route path="/compare" element={<ComparePage />} />

            <Route path="/data" element={<Navigate to="/settings/data" replace />} />

            <Route path="/settings" element={<SettingsLayout />}>

              <Route index element={<SettingsIndexRedirect />} />

              <Route path="data" element={<DataManagePage />} />

              <Route path="llm" element={<LlmProviderSettings />} />

            </Route>

          </Routes>

        </Content>

      </Layout>

    </Layout>

  );

}



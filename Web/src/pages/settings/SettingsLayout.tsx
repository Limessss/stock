import { Navigate, Outlet } from "react-router-dom";

/** 设置页路由容器；子项导航由左侧主菜单「系统设置」承担 */
export default function SettingsLayout() {
  return <Outlet />;
}

export function SettingsIndexRedirect() {
  return <Navigate to="/settings/data" replace />;
}

import {
  ArrowLeft,
  BarChart3,
  Bell,
  BookOpen,
  Bot,
  Boxes,
  ChartCandlestick,
  ChevronRight,
  CirclePlay,
  CloudDownload,
  Database,
  Download,
  Edit3,
  Eye,
  Flame,
  FlaskConical,
  Grid3X3,
  History,
  LineChart,
  Menu,
  Moon,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Settings,
  Sparkles,
  Star,
  Stethoscope,
  Sun,
  Trash2,
  TrendingUp,
  type LucideProps,
} from "lucide-react";
import type { ComponentType } from "react";

function icon(Icon: ComponentType<LucideProps>) {
  return function QdIcon(props: LucideProps) { return <Icon aria-hidden="true" size={16} strokeWidth={1.8} {...props} />; };
}

export const ArrowLeftOutlined = icon(ArrowLeft);
export const AppstoreOutlined = icon(Grid3X3);
export const BookOutlined = icon(BookOpen);
export const BulbFilled = icon(Sun);
export const BulbOutlined = icon(Moon);
export const CloudDownloadOutlined = icon(CloudDownload);
export const DashboardOutlined = icon(BarChart3);
export const DatabaseOutlined = icon(Database);
export const DeleteOutlined = icon(Trash2);
export const DownloadOutlined = icon(Download);
export const EditOutlined = icon(Edit3);
export const ExperimentOutlined = icon(FlaskConical);
export const EyeOutlined = icon(Eye);
export const FireOutlined = icon(Flame);
export const FundOutlined = icon(Boxes);
export const HistoryOutlined = icon(History);
export const LineChartOutlined = icon(LineChart);
export const MedicineBoxOutlined = icon(Stethoscope);
export const MenuOutlined = icon(Menu);
export const NotificationOutlined = icon(Bell);
export const OrderedListOutlined = icon(Menu);
export const PlayCircleOutlined = icon(CirclePlay);
export const PlusOutlined = icon(Plus);
export const RedoOutlined = icon(RotateCcw);
export const ReloadOutlined = icon(RefreshCw);
export const RightOutlined = icon(ChevronRight);
export const RiseOutlined = icon(TrendingUp);
export const RobotOutlined = icon(Bot);
export const SaveOutlined = icon(Save);
export const SearchOutlined = icon(Search);
export const SettingOutlined = icon(Settings);
export const StarFilled = icon(Star);
export const ThunderboltOutlined = icon(Sparkles);
export const BoldOutlined = icon(Bot);
export const ItalicOutlined = icon(Bot);
export const StrikethroughOutlined = icon(Bot);
export const UnorderedListOutlined = icon(Menu);
export const ChartOutlined = icon(ChartCandlestick);

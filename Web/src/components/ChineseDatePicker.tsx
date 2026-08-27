import { DatePicker, type DatePickerProps } from "@/components/ui";

/** 输入框与日历面板均使用中文习惯格式。 */
export const CN_DATE_FORMAT = "YYYY年MM月DD日";

export default function ChineseDatePicker(props: DatePickerProps) {
  return <DatePicker {...props} format={props.format ?? CN_DATE_FORMAT} />;
}

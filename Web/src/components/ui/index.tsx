import dayjs, { type Dayjs } from "dayjs";
import {
  Children,
  cloneElement,
  createContext,
  isValidElement,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";

type AnyProps = Record<string, any>;

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export function Space({ children, direction = "horizontal", size = 8, wrap, className, style, ...rest }: AnyProps) {
  const gap = Array.isArray(size) ? `${size[1]}px ${size[0]}px` : typeof size === "number" ? size : 8;
  return <div className={cx("qd-space", direction === "vertical" && "is-vertical", className)} style={{ gap, flexWrap: wrap ? "wrap" : undefined, ...style }} {...rest}>{children}</div>;
}
Space.Compact = function Compact({ children, className, style }: AnyProps) { return <div className={cx("qd-compact", className)} style={style}>{children}</div>; };

export function Row({ children, gutter = 0, align, justify, className, style, ...rest }: AnyProps) {
  const [x, y] = Array.isArray(gutter) ? gutter : [gutter, gutter];
  const alignItems = align === "middle" ? "center" : align === "bottom" ? "flex-end" : align === "top" ? "flex-start" : undefined;
  const justifyContent = justify === "start" ? "flex-start" : justify === "end" ? "flex-end" : justify === "center" ? "center" : justify === "space-around" ? "space-around" : justify === "space-between" ? "space-between" : justify === "space-evenly" ? "space-evenly" : undefined;
  return <div className={cx("qd-row", className)} style={{ columnGap: x, rowGap: y, alignItems, justifyContent, ...style }} {...rest}>{Children.map(children, (child) => isValidElement(child) ? cloneElement(child as ReactElement<AnyProps>, { __gutter: x }) : child)}</div>;
}

export function Col({ children, span, xs, sm, md, lg, xl, flex, __gutter = 0, className, style, ...rest }: AnyProps) {
  const isGrid = span != null || xs != null || sm != null || md != null || lg != null || xl != null;
  const clampSpan = (value: unknown, fallback: number) => value == null ? fallback : Math.max(1, Math.min(24, Number(typeof value === "object" ? (value as AnyProps).span : value) || fallback));
  const base = clampSpan(xs ?? span, 24);
  const smSpan = clampSpan(sm, base);
  const mdSpan = clampSpan(md, smSpan);
  const lgSpan = clampSpan(lg, mdSpan);
  const xlSpan = clampSpan(xl, lgSpan);
  const gridStyle = isGrid ? {
    "--qd-col-xs": `${base / 24 * 100}%`,
    "--qd-col-sm": `${smSpan / 24 * 100}%`,
    "--qd-col-md": `${mdSpan / 24 * 100}%`,
    "--qd-col-lg": `${lgSpan / 24 * 100}%`,
    "--qd-col-xl": `${xlSpan / 24 * 100}%`,
    "--qd-col-gap": `${__gutter || 0}px`,
  } : {};
  return <div className={cx("qd-col", isGrid && "is-grid", !isGrid && !flex && "is-auto", className)} style={{ ...(flex ? { flex, maxWidth: "100%" } : gridStyle), ...style }} {...rest}>{children}</div>;
}

export function Card({ children, title, extra, className, style, bodyStyle, headStyle, styles, bordered = true, hoverable, size, loading, ...rest }: AnyProps) {
  return <section className={cx("qd-card", !bordered && "is-borderless", hoverable && "is-hoverable", size === "small" && "is-small", className)} style={style} {...rest}>
    {(title || extra) && <header className="qd-card-head" style={{ ...headStyle, ...styles?.header }}><div className="qd-card-title">{title}</div><div>{extra}</div></header>}
    <div className="qd-card-body" style={{ ...bodyStyle, ...styles?.body }}>{loading ? <Spin /> : children}</div>
  </section>;
}

function Title({ level = 1, children, className, style, ...rest }: AnyProps) {
  const TagName = `h${Math.min(6, Math.max(1, level))}` as keyof JSX.IntrinsicElements;
  return <TagName className={cx("qd-title", className)} style={style} {...rest}>{children}</TagName>;
}
function Text({ children, type, strong, code, copyable, ellipsis, className, style, ...rest }: AnyProps) {
  const content = code ? <code>{children}</code> : children;
  return <span className={cx("qd-text", type && `is-${type}`, strong && "is-strong", ellipsis && "is-ellipsis", className)} style={style} title={typeof children === "string" && ellipsis ? children : undefined} {...rest}>{content}{copyable && <button className="qd-copy" onClick={() => navigator.clipboard?.writeText(String(children))}>复制</button>}</span>;
}
function Paragraph({ children, type, className, style, ...rest }: AnyProps) {
  return <p className={cx("qd-paragraph", type && `is-${type}`, className)} style={style} {...rest}>{children}</p>;
}
export const Typography = { Title, Text, Paragraph };

export function Button({ children, type = "default", danger, loading, disabled, icon, htmlType, block, className, style, onClick, ...rest }: AnyProps) {
  return <button type={htmlType ?? "button"} className={cx("qd-button", `is-${type}`, danger && "is-danger", block && "is-block", className)} style={style} disabled={disabled || loading} onClick={onClick} {...rest}>{loading ? <span className="qd-spinner" /> : icon}{children && <span>{children}</span>}</button>;
}

export function Tag({ children, color = "default", icon, closable, onClose, className, style, ...rest }: AnyProps) {
  return <span className={cx("qd-tag", `is-${String(color).replace("#", "hex-")}`, className)} style={style} {...rest}>{icon}{children}{closable && <button onClick={onClose}>×</button>}</span>;
}

export function Alert({ type = "info", message, description, showIcon = true, action, closable, className, style }: AnyProps) {
  const [visible, setVisible] = useState(true);
  if (!visible) return null;
  return <div className={cx("qd-alert", `is-${type}`, className)} style={style}>{showIcon && <span className="qd-alert-dot" />}<div className="qd-alert-content"><strong>{message}</strong>{description && <div>{description}</div>}</div>{action}{closable && <button onClick={() => setVisible(false)}>×</button>}</div>;
}

export function Divider({ children, orientation, className, style }: AnyProps) {
  return <div className={cx("qd-divider", orientation && `is-${orientation}`, className)} style={style}>{children && <span>{children}</span>}</div>;
}

export function Spin({ spinning = true, children, tip, size, className, style }: AnyProps) {
  if (children) return <div className={cx("qd-spin-wrap", spinning && "is-spinning", className)} style={style}>{children}{spinning && <div className="qd-spin-mask"><span className={cx("qd-spinner", size === "large" && "is-large")} />{tip}</div>}</div>;
  return spinning ? <span className={cx("qd-spinner", size === "large" && "is-large", className)} style={style} /> : null;
}

export function Empty({ description = "暂无数据", image, className, style }: AnyProps) {
  return <div className={cx("qd-empty", className)} style={style}>{image ?? <div className="qd-empty-icon">◇</div>}<div>{description}</div></div>;
}
Empty.PRESENTED_IMAGE_SIMPLE = null;

export function Statistic({ title, value, precision, suffix, prefix, valueStyle, className, style }: AnyProps) {
  const display = typeof value === "number" && precision != null ? value.toFixed(precision) : value;
  return <div className={cx("qd-stat", className)} style={style}><div className="qd-stat-title">{title}</div><div className="qd-stat-value" style={valueStyle}>{prefix}{display}{suffix}</div></div>;
}

export function Progress({ percent = 0, status, strokeColor, format, size, className, style }: AnyProps) {
  const safe = Math.max(0, Math.min(100, Number(percent) || 0));
  if (size === "small" || size?.[1]) return <div className={cx("qd-progress-line", status && `is-${status}`, className)} style={style}><div style={{ width: `${safe}%`, background: strokeColor }} /></div>;
  return <div className={cx("qd-progress", status && `is-${status}`, className)} style={style}><div className="qd-progress-line"><div style={{ width: `${safe}%`, background: strokeColor }} /></div><span>{format ? format(safe) : `${safe}%`}</span></div>;
}

export function Switch({ checked, defaultChecked, onChange, checkedChildren, unCheckedChildren, disabled, className, style }: AnyProps) {
  const [inner, setInner] = useState(!!defaultChecked);
  const active = checked ?? inner;
  return <button type="button" role="switch" aria-checked={active} className={cx("qd-switch", active && "is-checked", className)} style={style} disabled={disabled} onClick={() => { const next = !active; setInner(next); onChange?.(next); }}><span className="qd-switch-knob" /><span className="qd-switch-label">{active ? checkedChildren : unCheckedChildren}</span></button>;
}

export function Tooltip({ title, children }: AnyProps) {
  return <span className="qd-tooltip" data-tooltip={typeof title === "string" ? title : undefined}>{children}</span>;
}

export function Input(props: AnyProps) {
  const { prefix, suffix, addonBefore, addonAfter, className, style, allowClear, onChange, onPressEnter, onKeyDown, ...inputProps } = props;
  return <label className={cx("qd-input-wrap", className)} style={style}>{addonBefore}<span className="qd-input-prefix">{prefix}</span><input className="qd-input" onChange={onChange} onKeyDown={(event) => { if (event.key === "Enter") onPressEnter?.(event); onKeyDown?.(event); }} {...inputProps} />{allowClear && props.value && <button type="button" onClick={() => onChange?.({ target: { value: "" } })}>×</button>}<span>{suffix}</span>{addonAfter}</label>;
}
Input.TextArea = function TextArea({ className, style, autoSize, ...props }: AnyProps) { return <textarea className={cx("qd-textarea", className)} style={{ minHeight: autoSize ? 90 : undefined, ...style }} {...props} />; };
Input.Password = function Password(props: AnyProps) { return <Input {...props} type="password" />; };
Input.Search = function Search({ onSearch, enterButton, ...props }: AnyProps) { return <Input {...props} suffix={<Button type={enterButton ? "primary" : "default"} onClick={() => onSearch?.(props.value)}>搜索</Button>} onKeyDown={(e: any) => e.key === "Enter" && onSearch?.(e.currentTarget.value)} />; };

export function InputNumber({ value, defaultValue, onChange, formatter, parser, min, max, step, className, style, ...rest }: AnyProps) {
  const displayed = formatter ? formatter(value ?? defaultValue ?? "") : value ?? defaultValue ?? "";
  return <input type={formatter ? "text" : "number"} className={cx("qd-number", className)} style={style} value={displayed} min={min} max={max} step={step} onChange={(e) => { const raw = parser ? parser(e.target.value) : e.target.value === "" ? null : Number(e.target.value); onChange?.(raw); }} {...rest} />;
}

function normalizeOptions(children: ReactNode, options?: AnyProps[]) {
  if (options) return options;
  return Children.toArray(children).filter(isValidElement).map((child: any) => ({ value: child.props.value, label: child.props.children, disabled: child.props.disabled }));
}
export function Select({ value, defaultValue, onChange, options, children, placeholder, allowClear, mode, className, style, loading, disabled, optionLabelProp: _optionLabelProp, showSearch: _showSearch, filterOption: _filterOption, ...rest }: AnyProps) {
  const opts = normalizeOptions(children, options);
  const multiple = mode === "multiple" || mode === "tags";
  const normalized = multiple ? (value ?? defaultValue ?? []) : value ?? defaultValue ?? "";
  return <select className={cx("qd-select", className)} style={style} value={normalized} multiple={multiple} disabled={disabled || loading} onChange={(e) => {
    const selected = multiple ? Array.from(e.currentTarget.selectedOptions).map((o) => opts.find((item: AnyProps) => String(item.value) === o.value)?.value ?? o.value) : e.currentTarget.value;
    const selectedOption = multiple ? undefined : opts.find((o: AnyProps) => String(o.value) === String(selected));
    const selectedValue = selected === "" && allowClear ? undefined : selectedOption?.value ?? selected;
    onChange?.(multiple ? selected : selectedValue, selectedOption);
  }} {...rest}><option value="" disabled={!allowClear}>{loading ? "加载中…" : placeholder ?? "请选择"}</option>{opts.map((o: AnyProps) => <option key={String(o.value)} value={o.value} disabled={o.disabled}>{typeof o.label === "string" || typeof o.label === "number" ? o.label : String(o.value)}</option>)}</select>;
}
Select.Option = function Option(_props: AnyProps) { return null; };

export function Checkbox({ checked, defaultChecked, onChange, value, children, disabled, className, style }: AnyProps) {
  return <label className={cx("qd-check", className)} style={style}><input type="checkbox" checked={checked} defaultChecked={defaultChecked} value={value} disabled={disabled} onChange={onChange} /><span>{children}</span></label>;
}
Checkbox.Group = function CheckboxGroup({ value = [], onChange, children, className, style }: AnyProps) {
  const onGroupChange = (e: any) => { const next = e.target.checked ? [...value, e.target.value] : value.filter((v: any) => v !== e.target.value); onChange?.(next); };
  return <div className={className} style={style}>{Children.map(children, (child) => isValidElement(child) ? cloneElement(child as ReactElement<AnyProps>, { children: Children.map((child as ReactElement<AnyProps>).props.children, (nested) => isValidElement(nested) && (nested as ReactElement<AnyProps>).type === Checkbox ? cloneElement(nested as ReactElement<AnyProps>, { checked: value.includes((nested as ReactElement<AnyProps>).props.value), onChange: onGroupChange }) : nested) }) : child)}</div>;
};

function RadioItem({ value, children, checked, onChange, button }: AnyProps) {
  return <label className={cx(button ? "qd-radio-button" : "qd-radio", checked && "is-checked")}><input type="radio" value={value} checked={checked} onChange={onChange} /><span>{children}</span></label>;
}
export const Radio: AnyProps = (props: AnyProps) => <RadioItem {...props} />;
Radio.Group = function RadioGroup({ value, onChange, children, className, style }: AnyProps) { return <div className={cx("qd-radio-group", className)} style={style}>{Children.map(children, (child: any) => isValidElement(child) ? cloneElement(child as ReactElement<AnyProps>, { checked: (child as ReactElement<AnyProps>).props.value === value, onChange: (e: any) => onChange?.(e) }) : child)}</div>; };
Radio.Button = function RadioButton(props: AnyProps) { return <RadioItem {...props} button />; };

export type DatePickerProps = AnyProps;
export function DatePicker({ value, defaultValue, onChange, disabledDate, minDate, maxDate, className, style, placeholder, allowClear = true, format: _format, ...rest }: AnyProps) {
  const dateValue = value?.format ? value.format("YYYY-MM-DD") : defaultValue?.format ? defaultValue.format("YYYY-MM-DD") : "";
  const min = minDate?.format ? minDate.format("YYYY-MM-DD") : minDate;
  const max = maxDate?.format ? maxDate.format("YYYY-MM-DD") : maxDate;
  return <input type="date" className={cx("qd-date", className)} style={style} value={dateValue} min={min} max={max} placeholder={placeholder} onChange={(e) => { const next: Dayjs | null = e.target.value ? dayjs(e.target.value) : null; if (!next && !allowClear) return; if (next && disabledDate?.(next)) return; onChange?.(next, e.target.value); }} {...rest} />;
}

export interface ColumnType<T> { title?: ReactNode; dataIndex?: string | string[]; key?: string; width?: number | string; align?: "left" | "center" | "right"; fixed?: string; className?: string; sorter?: ((a: T, b: T) => number) | boolean; defaultSortOrder?: string; render?: (value: any, record: T, index: number) => ReactNode; ellipsis?: boolean; children?: ColumnType<T>[]; onCell?: (record: T, index?: number) => AnyProps; }
export type ColumnsType<T> = ColumnType<T>[];
function getValue(record: AnyProps, key?: string | string[]) { if (!key) return undefined; return (Array.isArray(key) ? key : [key]).reduce((v, k) => v?.[k], record); }
export function Table<T extends AnyProps>({ columns = [], dataSource = [], rowKey = "key", loading, pagination, scroll, size, className, style, onRow, rowClassName, locale, onChange, onScroll, wrapperRef }: AnyProps & { columns?: ColumnsType<T>; dataSource?: T[] }) {
  const leafColumns = useMemo(() => columns.flatMap((c: ColumnType<T>) => c.children?.length ? c.children : [c]), [columns]);
  const keyOf = (row: T, index: number) => (typeof rowKey === "function" ? rowKey(row) : row[rowKey]) ?? row.id ?? row.code ?? index;
  const defaultColumn = leafColumns.find((col: ColumnType<T>) => col.defaultSortOrder);
  const [sort, setSort] = useState<{ key: string; direction: "ascend" | "descend" } | null>(defaultColumn ? { key: String(defaultColumn.key ?? defaultColumn.dataIndex), direction: defaultColumn.defaultSortOrder === "ascend" ? "ascend" : "descend" } : null);
  const [page, setPage] = useState(Number(pagination?.current ?? pagination?.defaultCurrent ?? 1));
  const pageSize = Number(pagination?.pageSize ?? pagination?.defaultPageSize ?? 10);
  const sorted = useMemo(() => {
    if (!sort) return dataSource;
    const col = leafColumns.find((item: ColumnType<T>) => String(item.key ?? item.dataIndex) === sort.key);
    if (!col?.sorter) return dataSource;
    return [...dataSource].sort((a, b) => {
      const result = typeof col.sorter === "function" ? col.sorter(a, b) : String(getValue(a, col.dataIndex) ?? "").localeCompare(String(getValue(b, col.dataIndex) ?? ""), "zh-CN", { numeric: true });
      return sort.direction === "ascend" ? result : -result;
    });
  }, [dataSource, leafColumns, sort]);
  const rows = pagination === false ? sorted : sorted.slice((page - 1) * pageSize, page * pageSize);
  const changeSort = (col: ColumnType<T>) => {
    if (!col.sorter) return;
    const key = String(col.key ?? col.dataIndex);
    const next = sort?.key === key && sort.direction === "ascend" ? { key, direction: "descend" as const } : { key, direction: "ascend" as const };
    setSort(next);
    onChange?.({ current: page, pageSize }, {}, { columnKey: key, order: next.direction });
  };
  return <div ref={wrapperRef} onScroll={onScroll} className={cx("qd-table-wrap", size === "small" && "is-small", className)} style={style}>{loading && <div className="qd-table-loading"><Spin /></div>}<table className="qd-table" style={{ minWidth: scroll?.x }}><thead>{columns.some((c: ColumnType<T>) => c.children?.length) && <tr>{columns.map((col: ColumnType<T>, i: number) => <th key={i} colSpan={col.children?.length ?? 1} rowSpan={col.children?.length ? 1 : 2} style={{ width: col.width, textAlign: col.align }}>{col.title}</th>)}</tr>}<tr>{leafColumns.map((col: ColumnType<T>, i: number) => { const key = String(col.key ?? col.dataIndex ?? i); return <th key={key} className={cx(col.className, col.sorter && "is-sortable")} onClick={() => changeSort(col)} style={{ width: col.width, textAlign: col.align }}>{col.title}{sort?.key === key && <span className="qd-sort">{sort.direction === "ascend" ? "↑" : "↓"}</span>}</th>; })}</tr></thead><tbody>{rows.length ? rows.map((row: T, ri: number) => <tr key={keyOf(row, ri)} className={typeof rowClassName === "function" ? rowClassName(row, ri) : rowClassName} {...onRow?.(row, ri)}>{leafColumns.map((col: ColumnType<T>, ci: number) => { const value = getValue(row, col.dataIndex); const cellKey = col.key ?? (col.dataIndex != null ? String(col.dataIndex) : ci); return <td key={cellKey} className={col.className} style={{ width: col.width, textAlign: col.align }} {...col.onCell?.(row, ri)}>{col.render ? col.render(value, row, ri) : value == null ? "—" : String(value)}</td>; })}</tr>) : <tr><td colSpan={Math.max(1, leafColumns.length)}><Empty description={locale?.emptyText ?? "暂无数据"} /></td></tr>}</tbody></table>{pagination !== false && <Pagination {...(pagination === true || pagination == null ? {} : pagination)} current={page} pageSize={pageSize} total={pagination?.total ?? sorted.length} onChange={(nextPage: number, nextSize: number) => { setPage(nextPage); pagination?.onChange?.(nextPage, nextSize); onChange?.({ current: nextPage, pageSize: nextSize }, {}, sort ? { columnKey: sort.key, order: sort.direction } : {}); }} />}</div>;
}

export function Pagination({ current = 1, total = 0, pageSize = 10, onChange, showSizeChanger, pageSizeOptions = [10, 20, 50], className, style }: AnyProps) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return <div className={cx("qd-pagination", className)} style={style}><Button size="small" disabled={current <= 1} onClick={() => onChange?.(current - 1, pageSize)}>上一页</Button><span>{current} / {pages}</span><Button size="small" disabled={current >= pages} onClick={() => onChange?.(current + 1, pageSize)}>下一页</Button>{showSizeChanger && <Select value={pageSize} options={pageSizeOptions.map((n: number) => ({ label: `${n} 条/页`, value: n }))} onChange={(n: string) => onChange?.(1, Number(n))} />}</div>;
}

export function Descriptions({ children, title, column = 3, bordered, size, className, style }: AnyProps) {
  const count = typeof column === "number" ? column : column?.md ?? column?.sm ?? 2;
  return <div className={cx("qd-descriptions", bordered && "is-bordered", size === "small" && "is-small", className)} style={style}>{title && <div className="qd-descriptions-title">{title}</div>}<div className="qd-descriptions-grid" style={{ gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))` }}>{children}</div></div>;
}
Descriptions.Item = function DescriptionItem({ label, children, span = 1, className, style }: AnyProps) { return <div className={cx("qd-description", className)} style={{ gridColumn: `span ${span}`, ...style }}><div className="qd-description-label">{label}</div><div className="qd-description-value">{children}</div></div>; };

export function Collapse({ items, children, defaultActiveKey, className, style, ghost, size }: AnyProps) {
  const panels = items ?? Children.toArray(children).map((child: any) => ({ key: child.props.panelKey ?? child.key, label: child.props.header, children: child.props.children, extra: child.props.extra }));
  const defaults = Array.isArray(defaultActiveKey) ? defaultActiveKey : defaultActiveKey != null ? [defaultActiveKey] : [];
  return <div className={cx("qd-collapse", ghost && "is-ghost", size === "small" && "is-small", className)} style={style}>{panels.map((panel: AnyProps) => <details key={panel.key} open={defaults.map(String).includes(String(panel.key))}><summary>{panel.label}<span>{panel.extra}</span></summary><div className="qd-collapse-body">{panel.children}</div></details>)}</div>;
}
Collapse.Panel = function Panel() { return null; };

export const List: any = function List({ dataSource = [], renderItem, children, loading, header, footer, bordered, split = true, className, style, locale }: AnyProps) {
  return <div className={cx("qd-list", bordered && "is-bordered", !split && "no-split", className)} style={style}>{header && <div className="qd-list-header">{header}</div>}{loading ? <Spin /> : dataSource.length ? dataSource.map((item: any, i: number) => <div key={item?.id ?? item?.key ?? i}>{renderItem?.(item, i)}</div>) : children ?? <Empty description={locale?.emptyText ?? "暂无数据"} />}{footer && <div className="qd-list-footer">{footer}</div>}</div>;
}
List.Item = function ListItem({ children, actions, extra, className, style }: AnyProps) { return <div className={cx("qd-list-item", className)} style={style}><div className="qd-list-content">{children}</div>{extra}{actions && <div className="qd-list-actions">{actions}</div>}</div>; };
List.Item.Meta = function ListMeta({ avatar, title, description }: AnyProps) { return <div className="qd-list-meta">{avatar}<div><div className="qd-list-meta-title">{title}</div><div className="qd-list-meta-description">{description}</div></div></div>; };

export function Timeline({ children, items, className, style }: AnyProps) {
  const content = items ? items.map((item: AnyProps, i: number) => <Timeline.Item key={item.key ?? i} {...item}>{item.children}</Timeline.Item>) : children;
  return <div className={cx("qd-timeline", className)} style={style}>{content}</div>;
}
Timeline.Item = function TimelineItem({ children, label, color, dot, className, style }: AnyProps) { return <div className={cx("qd-timeline-item", className)} style={style}><div className="qd-timeline-label">{label}</div><div className="qd-timeline-rail"><span style={{ borderColor: color, color }}>{dot ?? ""}</span></div><div className="qd-timeline-content">{children}</div></div>; };

export function Breadcrumb({ items = [], className, style }: AnyProps) { return <nav className={cx("qd-breadcrumb", className)} style={style}>{items.map((item: AnyProps, i: number) => <span key={i}>{item.href ? <a href={item.href}>{item.title}</a> : item.title}{i < items.length - 1 && <b>/</b>}</span>)}</nav>; }

export function Segmented({ options = [], value, onChange, className, style }: AnyProps) { return <div className={cx("qd-segmented", className)} style={style}>{options.map((option: any) => { const item = typeof option === "object" ? option : { label: option, value: option }; return <button key={String(item.value)} className={value === item.value ? "is-active" : ""} onClick={() => onChange?.(item.value)}>{item.icon}{item.label}</button>; })}</div>; }

export function Skeleton({ active, paragraph = true, className, style }: AnyProps) { return <div className={cx("qd-skeleton", active && "is-active", className)} style={style}><i />{paragraph && <><i /><i /></>}</div>; }
Skeleton.Input = function SkeletonInput({ active, className, style }: AnyProps) { return <span className={cx("qd-skeleton-input", active && "is-active", className)} style={style} />; };

export function Popconfirm({ title, description, onConfirm, onCancel, children, okText = "确定", cancelText = "取消" }: AnyProps) {
  const [open, setOpen] = useState(false);
  return <span className="qd-popconfirm"><span onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen(!open); }}>{children}</span>{open && <span className="qd-popconfirm-panel"><strong>{title}</strong>{description && <small>{description}</small>}<span><Button size="small" onClick={() => { onCancel?.(); setOpen(false); }}>{cancelText}</Button><Button size="small" type="primary" onClick={() => { onConfirm?.(); setOpen(false); }}>{okText}</Button></span></span>}</span>;
}

export function Modal({ open, title, children, onCancel, onOk, footer, width = 640, confirmLoading, okText = "确定", cancelText = "取消", okButtonProps, destroyOnClose, className, styles }: AnyProps) {
  if (!open) return destroyOnClose ? null : null;
  return <div className="qd-modal-root" role="dialog" aria-modal="true"><div className="qd-modal-backdrop" onClick={onCancel} /><div className={cx("qd-modal", className)} style={{ width, ...styles?.wrapper }}><header><div>{title}</div><button onClick={onCancel}>×</button></header><div className="qd-modal-body" style={styles?.body}>{children}</div>{footer !== null && <footer>{footer ?? <><Button onClick={onCancel}>{cancelText}</Button><Button type="primary" loading={confirmLoading} onClick={onOk} {...okButtonProps}>{okText}</Button></>}</footer>}</div></div>;
}

type ToastType = "success" | "error" | "warning" | "info";
function toast(type: ToastType, content: ReactNode) {
  const host = document.getElementById("qd-toast-host") ?? Object.assign(document.body.appendChild(document.createElement("div")), { id: "qd-toast-host" });
  const item = document.createElement("div"); item.className = `qd-toast is-${type}`; item.textContent = typeof content === "string" ? content : String(content); host.appendChild(item); setTimeout(() => item.remove(), 3200);
}
export const message = { success: (c: ReactNode) => toast("success", c), error: (c: ReactNode) => toast("error", c), warning: (c: ReactNode) => toast("warning", c), info: (c: ReactNode) => toast("info", c) };

const appApi = {
  message,
  modal: {
    confirm: ({ title, content, onOk, onCancel }: AnyProps) => { if (window.confirm(`${title ?? "确认"}${content ? `\n${typeof content === "string" ? content : ""}` : ""}`)) return onOk?.(); return onCancel?.(); },
  },
  notification: { success: ({ message: m }: AnyProps) => toast("success", m), error: ({ message: m }: AnyProps) => toast("error", m) },
};
export const App = { useApp: () => appApi };

type FormApi = { setFieldsValue: (values: AnyProps) => void; setFieldValue: (name: string, value: any) => void; getFieldsValue: () => AnyProps; getFieldValue: (name: string) => any; resetFields: () => void; validateFields: () => Promise<AnyProps>; __subscribe?: (fn: (v: AnyProps) => void) => () => void; __set?: (name: string, value: any) => void; __initial?: AnyProps; __onValuesChange?: (changed: AnyProps, all: AnyProps) => void };
function createForm(): FormApi { let values: AnyProps = {}; const listeners = new Set<(v: AnyProps) => void>(); const notify = () => listeners.forEach((fn) => fn(values)); return { setFieldsValue(next) { values = { ...values, ...next }; notify(); }, setFieldValue(name, value) { values = { ...values, [name]: value }; notify(); }, getFieldsValue: () => values, getFieldValue: (name) => values[name], resetFields() { values = {}; notify(); }, validateFields: async () => values, __subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }, __set(name, value) { values = { ...values, [name]: value }; notify(); } }; }
const FormContext = createContext<FormApi | null>(null);
export function Form({ children, form, initialValues, onFinish, onValuesChange, className, style, ...rest }: AnyProps) {
  const api = useMemo(() => form ?? createForm(), [form]);
  const initialized = useRef(false);
  useEffect(() => { if (!initialized.current) { initialized.current = true; api.__initial = initialValues; api.setFieldsValue(initialValues ?? {}); } }, [api, initialValues]);
  api.__onValuesChange = onValuesChange;
  return <FormContext.Provider value={api}><form className={cx("qd-form", className)} style={style} onSubmit={async (e) => { e.preventDefault(); onFinish?.(await api.validateFields()); }} {...rest}>{children}</form></FormContext.Provider>;
}
Form.useForm = function useForm() { return useState<FormApi>(() => createForm()); };
Form.Item = function FormItem({ name, label, required, extra, children, className, style, valuePropName = "value" }: AnyProps) { const api = useContext(FormContext); const [, rerender] = useState({}); useEffect(() => api?.__subscribe?.(() => rerender({})), [api]); const current = name ? api?.getFieldsValue()[name] : undefined; const child = isValidElement(children) && name ? cloneElement(children as ReactElement<AnyProps>, { [valuePropName]: current ?? (valuePropName === "checked" ? false : ""), onChange: (e: any) => { const value = e?.target ? (valuePropName === "checked" ? e.target.checked : e.target.value) : e; api?.__set?.(name, value); (children as ReactElement<AnyProps>).props.onChange?.(e); api?.__onValuesChange?.({ [name]: value }, api.getFieldsValue()); } }) : children; return <label className={cx("qd-form-item", className)} style={style}>{label && <span className="qd-form-label">{label}{required && <b>*</b>}</span>}{child}{extra && <small>{extra}</small>}</label>; };

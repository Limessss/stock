import { useEffect, useMemo, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {

  Alert,

  Breadcrumb,

  Button,

  Card,

  Col,

  Divider,

  Form,

  Input,

  List,

  Popconfirm,

  Row,

  Space,

  Spin,

  Switch,

  Tag,

  Typography,

  message,

} from "antd";

import { ArrowLeftOutlined, ReloadOutlined, RobotOutlined, SaveOutlined } from "@ant-design/icons";

import { Link, useNavigate, useParams } from "react-router-dom";



import {

  getStrategyDetail,

  resetStrategyDefaults,

  resetStrategyMeta,

  updateStrategyConfig,

} from "@/api/strategies";

import ParamForm from "@/components/ParamForm";



const { Title, Text } = Typography;



export default function StrategyDetailPage() {

  const { name = "" } = useParams<{ name: string }>();

  const navigate = useNavigate();

  const queryClient = useQueryClient();



  const [label, setLabel] = useState("");

  const [description, setDescription] = useState("");

  const [isDefault, setIsDefault] = useState(false);

  const [params, setParams] = useState<Record<string, unknown>>({});

  const [dirty, setDirty] = useState(false);



  const detailQ = useQuery({

    queryKey: ["strategy", name],

    queryFn: () => getStrategyDetail(name),

    enabled: !!name,

  });



  useEffect(() => {

    if (!detailQ.data) return;

    setLabel(detailQ.data.label);

    setDescription(detailQ.data.description ?? "");

    setIsDefault(!!detailQ.data.is_default);

    setParams(detailQ.data.default_params);

    setDirty(false);

  }, [detailQ.data]);



  const baseline = useMemo(() => {

    if (!detailQ.data) return null;

    return {

      label: detailQ.data.label,

      description: detailQ.data.description ?? "",

      isDefault: !!detailQ.data.is_default,

      params: detailQ.data.default_params,

    };

  }, [detailQ.data]);



  const markDirty = (

    next: Partial<{

      label: string;

      description: string;

      isDefault: boolean;

      params: Record<string, unknown>;

    }>

  ) => {

    if (!baseline) return;

    const merged = {

      label: next.label ?? label,

      description: next.description ?? description,

      isDefault: next.isDefault ?? isDefault,

      params: next.params ?? params,

    };

    const changed =

      merged.label !== baseline.label ||

      merged.description !== baseline.description ||

      merged.isDefault !== baseline.isDefault ||

      Object.keys(merged.params).some((k) => merged.params[k] !== baseline.params[k]);

    setDirty(changed);

  };



  const saveMut = useMutation({

    mutationFn: () =>

      updateStrategyConfig(name, {

        label: label.trim(),

        description,

        is_default: isDefault,

        params,

      }),

    onSuccess: (data) => {

      message.success("策略配置已保存");

      setLabel(data.label);

      setDescription(data.description ?? "");

      setIsDefault(!!data.is_default);

      setParams(data.default_params);

      setDirty(false);

      queryClient.setQueryData(["strategy", name], data);

      queryClient.invalidateQueries({ queryKey: ["strategies"] });

    },

    onError: (e: Error) => message.error(e.message),

  });



  const resetParamsMut = useMutation({

    mutationFn: () => resetStrategyDefaults(name),

    onSuccess: (data) => {

      message.success("默认参数已恢复为内置值");

      setParams(data.default_params);

      queryClient.setQueryData(["strategy", name], data);

      queryClient.invalidateQueries({ queryKey: ["strategies"] });

      markDirty({ params: data.default_params });

    },

    onError: (e: Error) => message.error(e.message),

  });



  const resetMetaMut = useMutation({

    mutationFn: () => resetStrategyMeta(name),

    onSuccess: (data) => {

      message.success("名称与说明已恢复为内置值");

      setLabel(data.label);

      setDescription(data.description ?? "");

      setIsDefault(!!data.is_default);

      queryClient.setQueryData(["strategy", name], data);

      queryClient.invalidateQueries({ queryKey: ["strategies"] });

      markDirty({

        label: data.label,

        description: data.description ?? "",

        isDefault: !!data.is_default,

      });

    },

    onError: (e: Error) => message.error(e.message),

  });



  const paramChangedCount = useMemo(() => {

    if (!detailQ.data) return 0;

    const code = detailQ.data.code_defaults;

    return Object.keys(params).filter((k) => params[k] !== code[k]).length;

  }, [detailQ.data, params]);



  if (!name) {

    return <Alert type="error" message="缺少策略标识" showIcon />;

  }



  return (

    <Space direction="vertical" size="middle" style={{ width: "100%" }}>

      <Breadcrumb

        items={[

          { title: <Link to="/strategies">策略模型</Link> },

          { title: label || name },

        ]}

      />



      <Card>

        <Space style={{ width: "100%", justifyContent: "space-between" }} wrap>

          <Space>

            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/strategies")}>

              返回列表

            </Button>

            <Link to={`/tuning?strategy=${name}`}>

              <Button icon={<RobotOutlined />}>AI 调参</Button>

            </Link>

            <div>

              <Title level={4} style={{ margin: 0 }}>

                {label || name}

              </Title>

              <Text type="secondary" code>

                {name}

              </Text>

            </div>

          </Space>

          <Space wrap>

            <Popconfirm

              title="恢复名称与说明？"

              description="将清除自定义展示名称和策略说明"

              onConfirm={() => resetMetaMut.mutate()}

              okText="恢复"

              cancelText="取消"

              disabled={!detailQ.data?.has_custom_meta}

            >

              <Button loading={resetMetaMut.isPending} disabled={!detailQ.data?.has_custom_meta}>

                恢复名称说明

              </Button>

            </Popconfirm>

            <Popconfirm

              title="恢复默认参数？"

              description="将清除此策略的自定义默认参数"

              onConfirm={() => resetParamsMut.mutate()}

              okText="恢复"

              cancelText="取消"

              disabled={!detailQ.data?.has_custom_defaults}

            >

              <Button

                icon={<ReloadOutlined />}

                loading={resetParamsMut.isPending}

                disabled={!detailQ.data?.has_custom_defaults}

              >

                恢复默认参数

              </Button>

            </Popconfirm>

            <Button

              type="primary"

              icon={<SaveOutlined />}

              loading={saveMut.isPending}

              disabled={!dirty || !label.trim()}

              onClick={() => saveMut.mutate()}

            >

              保存配置

            </Button>

          </Space>

        </Space>

      </Card>



      {detailQ.isLoading ? (

        <Card>

          <Spin spinning>

            <div style={{ minHeight: 240 }} />

          </Spin>

        </Card>

      ) : detailQ.error ? (

        <Alert type="error" message="加载失败" description={(detailQ.error as Error).message} showIcon />

      ) : detailQ.data ? (

        <>

          <Card title="基本信息">

            <Form layout="vertical">

              <Row gutter={16}>

                <Col xs={24} md={12}>

                  <Form.Item label="策略名称（展示用）" required>

                    <Input

                      value={label}

                      maxLength={64}

                      placeholder={detailQ.data.code_label}

                      onChange={(e) => {

                        setLabel(e.target.value);

                        markDirty({ label: e.target.value });

                      }}

                    />

                  </Form.Item>

                </Col>

                <Col xs={24} md={12}>

                  <Form.Item label="策略标识" extra="系统内部 ID，不可修改">

                    <Input value={name} disabled />

                  </Form.Item>

                </Col>

                <Col span={24}>

                  <Form.Item label="策略说明">

                    <Input.TextArea

                      value={description}

                      rows={4}

                      maxLength={2000}

                      placeholder={detailQ.data.code_description || "请输入策略说明"}

                      onChange={(e) => {

                        setDescription(e.target.value);

                        markDirty({ description: e.target.value });

                      }}

                    />

                  </Form.Item>

                </Col>

                <Col span={24}>

                  <Form.Item

                    label="设为默认策略"

                    extra="开启后，选股扫描、回测、个股诊断等页面将默认选中此策略"

                  >

                    <Switch

                      checked={isDefault}

                      checkedChildren="默认"

                      unCheckedChildren="否"

                      onChange={(checked) => {

                        setIsDefault(checked);

                        markDirty({ isDefault: checked });

                      }}

                    />

                    {isDefault && (

                      <Tag color="gold" style={{ marginLeft: 12 }}>

                        当前为全局默认策略

                      </Tag>

                    )}

                  </Form.Item>

                </Col>

              </Row>

            </Form>

          </Card>



          <Row gutter={[16, 16]}>

            <Col xs={24} lg={14}>

              <Card title="核心逻辑（只读）">

                <List

                  size="small"

                  dataSource={detailQ.data.features}

                  locale={{ emptyText: "暂无" }}

                  renderItem={(item) => <List.Item style={{ paddingInline: 0 }}>• {item}</List.Item>}

                />

              </Card>

            </Col>

            <Col xs={24} lg={10}>

              <Card title="评分分级（只读）">

                <List

                  size="small"

                  dataSource={detailQ.data.tier_rules}

                  locale={{ emptyText: "暂无" }}

                  renderItem={(item) => <List.Item style={{ paddingInline: 0 }}>{item}</List.Item>}

                />

                <Divider />

                <Space wrap>

                  {detailQ.data.has_custom_meta && <Tag color="purple">已自定义名称/说明</Tag>}

                  {detailQ.data.has_custom_defaults && <Tag color="blue">已自定义默认参数</Tag>}

                  {paramChangedCount > 0 && dirty && (

                    <Tag color="orange">未保存参数变更 {paramChangedCount} 项</Tag>

                  )}

                </Space>

              </Card>

            </Col>

          </Row>



          <Card title="默认参数">

            <Alert

              type="info"

              showIcon

              style={{ marginBottom: 16 }}

              message="默认参数与默认策略"

              description="保存后，扫描/回测/诊断在未手动改参时使用此处参数；设为默认策略后，上述页面会默认选中本策略。"

            />

            <ParamForm

              schema={detailQ.data.params_schema}

              value={params}

              onChange={(next) => {

                setParams(next);

                markDirty({ params: next });

              }}

            />

          </Card>

        </>

      ) : null}

    </Space>

  );

}



import { useQuery } from "@tanstack/react-query";
import { Card, Empty, Space, Spin, Table, Tag, Typography } from "antd";
import { AppstoreOutlined, RightOutlined, StarFilled } from "@ant-design/icons";
import { Link } from "react-router-dom";
import type { ColumnsType } from "antd/es/table";

import { fetchStrategies, type StrategyInfo } from "@/api/strategies";

const { Title, Paragraph, Text } = Typography;

export default function StrategiesPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["strategies"],
    queryFn: fetchStrategies,
    staleTime: 60_000,
  });

  const columns: ColumnsType<StrategyInfo> = [
    {
      title: "策略名称",
      dataIndex: "label",
      render: (label, row) => (
        <Space direction="vertical" size={0}>
          <Space size={6}>
            <Link to={`/strategies/${row.name}`}>
              <Text strong>{label}</Text>
            </Link>
            {row.is_default && (
              <Tag icon={<StarFilled />} color="gold">
                默认
              </Tag>
            )}
          </Space>
          <Text type="secondary" code style={{ fontSize: 12 }}>
            {row.name}
          </Text>
        </Space>
      ),
    },
    {
      title: "说明",
      dataIndex: "description",
      ellipsis: true,
      render: (desc: string) => desc || "—",
    },
    {
      title: "参数数量",
      dataIndex: "param_count",
      width: 100,
      align: "center",
      render: (n: number) => n ?? "—",
    },
    {
      title: "自定义",
      key: "custom",
      width: 160,
      render: (_, row) => (
        <Space wrap size={4}>
          {row.has_custom_meta && <Tag color="purple">名称/说明</Tag>}
          {row.has_custom_defaults ? (
            <Tag color="blue">默认参数</Tag>
          ) : (
            <Tag>参数内置</Tag>
          )}
        </Space>
      ),
    },
    {
      title: "",
      key: "action",
      width: 80,
      align: "center",
      render: (_, row) => (
        <Link to={`/strategies/${row.name}`}>
          详情 <RightOutlined />
        </Link>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card>
        <Space align="start">
          <AppstoreOutlined style={{ fontSize: 28, color: "#1677ff" }} />
          <div>
            <Title level={4} style={{ margin: 0 }}>
              策略模型
            </Title>
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              编辑策略名称、说明与默认参数，并指定全局默认策略。扫描、回测、诊断将自动应用这些配置。
              {data?.default_strategy && (
                <>
                  {" "}
                  当前默认：
                  <Text code>{data.default_strategy}</Text>
                </>
              )}
            </Paragraph>
          </div>
        </Space>
      </Card>

      <Card title={`策略列表（${data?.strategies.length ?? 0}）`}>
        {isLoading ? (
          <Spin spinning>
            <div style={{ minHeight: 200 }} />
          </Spin>
        ) : error ? (
          <Empty description={(error as Error).message} />
        ) : (
          <Table
            rowKey="name"
            columns={columns}
            dataSource={data?.strategies ?? []}
            pagination={false}
            size="middle"
          />
        )}
      </Card>
    </Space>
  );
}

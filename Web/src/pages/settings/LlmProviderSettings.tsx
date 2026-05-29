import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Card, Form, Input, InputNumber, Space, Tag, Typography } from "antd";
import { SaveOutlined, ThunderboltOutlined } from "@ant-design/icons";

import { getLlmSettings, testLlmSettings, updateLlmSettings } from "@/api/settings";

const { Title, Paragraph, Text } = Typography;

export default function LlmProviderSettings() {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const [form] = Form.useForm();
  const [apiKeyEdited, setApiKeyEdited] = useState(false);

  const settingsQ = useQuery({
    queryKey: ["settings", "llm"],
    queryFn: getLlmSettings,
  });

  useEffect(() => {
    if (settingsQ.data) {
      form.setFieldsValue({
        base_url: settingsQ.data.base_url,
        model: settingsQ.data.model,
        timeout: settingsQ.data.timeout ?? 60,
        api_key: "",
      });
      setApiKeyEdited(false);
    }
  }, [settingsQ.data, form]);

  const saveMut = useMutation({
    mutationFn: async () => {
      const v = await form.validateFields();
      return updateLlmSettings({
        base_url: String(v.base_url).trim(),
        model: String(v.model).trim(),
        timeout: v.timeout ?? 60,
        api_key: v.api_key || "",
      });
    },
    onSuccess: (data) => {
      message.success("大模型提供商配置已保存");
      qc.setQueryData(["settings", "llm"], data);
      form.setFieldValue("api_key", "");
      setApiKeyEdited(false);
    },
    onError: (e: Error) => message.error(e.message),
  });

  const testMut = useMutation({
    mutationFn: testLlmSettings,
    onSuccess: (data) => message.success(`连接成功 (${data.latency_ms}ms)：${data.reply}`),
    onError: (e: Error) => message.error(e.message),
  });

  const handleTest = async () => {
    const apiKey = String(form.getFieldValue("api_key") ?? "").trim();
    const configured = settingsQ.data?.configured;

    if (apiKeyEdited && apiKey) {
      message.warning("请先点击「保存」，再测试连接");
      return;
    }
    if (!configured) {
      message.warning("请先填写 API Key 并保存后再测试连接");
      return;
    }
    testMut.mutate();
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card>
        <Title level={4} style={{ marginTop: 0 }}>
          大模型提供商
        </Title>
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          配置 OpenAI 兼容接口（OpenAI、DeepSeek、通义、本地 vLLM 等）。AI 调参等功能将使用此处配置。
          Key 保存在本地 <Text code>data/cache/system_settings.json</Text>。
        </Paragraph>
        {settingsQ.data && (
          <div style={{ marginTop: 12 }}>
            {settingsQ.data.configured ? (
              <Tag color="success">已配置 · {settingsQ.data.api_key_masked}</Tag>
            ) : (
              <Tag color="warning">未配置 API Key</Tag>
            )}
          </div>
        )}
      </Card>

      <Card>
        <Form
          form={form}
          layout="vertical"
          initialValues={{ timeout: 60 }}
          onFinish={() => saveMut.mutate()}
        >
          <Form.Item
            name="base_url"
            label="API Base URL"
            rules={[{ required: true, message: "请输入 Base URL" }]}
          >
            <Input placeholder="https://api.deepseek.com/v1" />
          </Form.Item>
          <Form.Item name="model" label="默认模型" rules={[{ required: true, message: "请输入模型名称" }]}>
            <Input placeholder="deepseek-chat / gpt-4o-mini" />
          </Form.Item>
          <Form.Item
            name="timeout"
            label="请求超时（秒）"
            rules={[{ required: true, message: "请设置超时时间" }]}
          >
            <InputNumber min={5} max={300} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            extra={
              settingsQ.data?.configured && !apiKeyEdited
                ? `当前：${settingsQ.data.api_key_masked}（留空则不修改）`
                : "留空则不修改已有 Key"
            }
          >
            <Input.Password placeholder="sk-..." onChange={() => setApiKeyEdited(true)} />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saveMut.isPending}>
              保存
            </Button>
            <Button icon={<ThunderboltOutlined />} loading={testMut.isPending} onClick={handleTest}>
              测试连接
            </Button>
          </Space>
        </Form>
      </Card>

      {!settingsQ.data?.configured && (
        <Alert
          type="info"
          showIcon
          message="配置完成后即可使用「AI 调参」功能"
          description="请填写 API Key 并保存，然后点击测试连接确认可用。"
        />
      )}
    </Space>
  );
}

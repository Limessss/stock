import { Empty, Card } from "antd";

interface Props {
  title: string;
  description?: string;
}

export default function PlaceholderPage({ title, description }: Props) {
  return (
    <Card title={title}>
      <Empty
        description={description ?? "本页将在后续 Phase 实现"}
      />
    </Card>
  );
}

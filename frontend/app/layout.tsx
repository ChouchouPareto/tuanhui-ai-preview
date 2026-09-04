import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "团绘AI｜本地生活一键生图",
  description: "上传门店与菜品素材，确认真实信息后一键生成团购首页五图",
  icons: { icon: "/brand/tuanhui-logo-mark.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

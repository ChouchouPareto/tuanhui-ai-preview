import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "团绘AI｜门店信息采集",
  description: "上传菜单与门头，确认真实经营信息",
  icons: { icon: "/brand/tuanhui-logo-mark.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

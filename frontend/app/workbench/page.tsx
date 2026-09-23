"use client";
import {useEffect,useState} from "react";
import Link from "next/link";
import {adminRequest} from "../../lib/admin-client";
import "./workbench.css";
type Contract={text_model:string;vision_model:string;image_model:string;credential_configured:boolean;max_text_calls:number};
export default function AdminWorkbench(){
  const [contract,setContract]=useState<Contract|null>(null),[error,setError]=useState("");
  useEffect(()=>{let live=true;adminRequest<Contract>("/contracts").then(v=>{if(live)setContract(v);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[]);
  return <main className="functional-workbench"><header><h1>团绘 · 产品后台</h1><Link href={process.env.NEXT_PUBLIC_PRODUCT_ORIGIN||"http://127.0.0.1:3011"}>打开团绘前台</Link></header>
    <p>仅供内部团队使用，不是商家经营后台。当前提供模板审核和模型状态查询。</p>
    {error&&<p role="alert" className="wb-error">{error}</p>}
    <section><h2>构图模板</h2><p>审核区域结构与备注；现有模板仍是内部预览，审核记录不代表已经通过成品质量验收。</p><Link href="/workbench/templates">进入模板审核</Link></section>
    <section><h2>模型运行配置 · 只读</h2>{contract?<dl><dt>语言理解</dt><dd>{contract.text_model}</dd><dt>视觉理解</dt><dd>{contract.vision_model}</dd><dt>图片生成</dt><dd>{contract.image_model}</dd><dt>模型凭据</dt><dd>{contract.credential_configured?"已配置（不显示密钥）":"未配置"}</dd><dt>单轮语言调用上限</dt><dd>{contract.max_text_calls} 次，不自动重试</dd></dl>:<p role="status">{error?"未取得配置":"正在读取配置…"}</p>}</section>
    <section><h2>待建设</h2><p>PE 发布与回滚、集中任务排查、评测管理、多人管理员账号尚未接入本页。不会用空按钮冒充已完成。</p></section>
  </main>;
}

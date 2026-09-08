export type Question = { field: string; question: string };
export type StoreNameCandidate = { name: string; aliases: string[]; region?: string | null; evidence: string; confidence: number };
export type MenuProduct = { name: string; category?: string | null; price_original?: string | null; specification?: string | null; confidence: number; needs_confirmation: boolean };
export type Facts = Record<string, unknown>;
export type Coverage = { fact_version: number; facts: Facts; questions: Question[]; ready_for_confirmation: boolean };
export type Asset = { id: string; asset_type?: string; semantic_role: string; subcategory?: string | null; priority: number; is_hero: boolean; original_name: string; preview_path?: string; width?: number | null; height?: number | null };

export const ROLE_NAMES: Record<string, string> = {
  menu: "菜单", storefront: "门头", signature_dish: "招牌菜", dish: "菜品",
  environment: "环境", logo: "Logo", credential: "资质", other: "其他",
};

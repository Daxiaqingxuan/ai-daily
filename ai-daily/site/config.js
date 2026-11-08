/* 入口配置：siteUrl 固定线上入口，桌面用本地文件打开时也能分享出可访问的链接 */
window.AI_DAILY_CONFIG = {
  name: "AI 晨报",
  siteUrl: "__SITE_URL__",
  /* 内容声明的唯一事实源：报尾 / 样张 / 模板 / README 由 apply_disclaimer.py 派生，
     分享面板在运行时读同一个常量。改文案只改这一行，然后跑脚本 + build_index + 发布。 */
  disclaimer: "本报内容由 AI 自动生成，用于产品演示，不构成事实报道。"
};

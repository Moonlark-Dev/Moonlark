import { defineConfig } from 'vitepress'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  title: "Moonlark 开发文档",
  description: "The document for Moonlark developers",
  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    nav: [
      { text: '首页', link: '/' },
      {
	      text: '快速开始',
	      items: [
		      { text: '前言', link: "/quick-start" },
		      { text: '搭建开发环境', link: "/quick-start/create-develop-environment" },
		      { text: '第一个 Moonlark 插件', link: "/quick-start/first-plugin" },
		      { text: '发生了什么？', link: "/quick-start/what-happened" },
		      { text: '插件帮助', link: "/quick-start/plugin-help" }
	      ]
      },
      { text: '插件', link: '/plugins' },
    ],

    sidebar: [],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/Moonlark-Dev/Moonlark' }
    ]
  }
})

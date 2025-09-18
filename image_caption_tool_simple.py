#!/usr/bin/env python3
"""
图片描述生成工具 - 独立GUI版本（简化版）
基于已有核心代码开发的图片描述生成工具，支持批量处理和多种模型
"""

import os
import sys
import json
import time
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import requests
from io import BytesIO


@dataclass
class ImageDescription:
    """图片描述数据类 - 复用已有代码"""
    frame_path: str
    original_description: str
    modified_description: str = ""
    timestamp: float = 0.0
    frame_number: int = 0
    confidence: float = 0.0
    language: str = "zh"
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if not self.modified_description:
            self.modified_description = self.original_description

    @property
    def current_description(self) -> str:
        """获取当前描述（优先使用修改后的）"""
        return self.modified_description or self.original_description


class ImageCaptionGenerator:
    """图片描述生成器 - 集成已有核心逻辑"""
    
    def __init__(self):
        # 默认配置 - 新增：GUI专用配置
        self.config = {
            'api_timeout': 30,
            'max_retries': 3,
            'max_concurrent': 3,
            'test_mode': True,  # 默认使用测试模式，避免API依赖
            'description_styles': {
                '简洁': '请简洁描述这张图片中的主要内容，控制在50字以内。',
                '详细': '请详细描述这张图片，包括物体、场景、颜色、光线、动作等，控制在150字以内。',
                '场景化': '请以场景化的方式描述这张图片，营造氛围感，控制在100字以内。'
            },
            'models': {
                '本地测试模式': {
                    'type': 'local',
                    'model': 'test',
                    'api_key': None
                },
                'Hugging Face BLIP (免费)': {
                    'type': 'huggingface',
                    'model': 'Salesforce/blip-image-captioning-base',
                    'api_key': None  # 公开模型无需API密钥
                },
                'Hugging Face GIT (免费)': {
                    'type': 'huggingface',
                    'model': 'microsoft/git-large-coco',
                    'api_key': None
                }
            }
        }
        
        # 当前设置
        self.current_model = '本地测试模式'
        self.current_style = '简洁'
        
        # 测试用的模拟描述
        self.mock_descriptions = [
            "一只可爱的小猫坐在窗台上，阳光透过窗户洒在它身上",
            "繁忙的城市街道，高楼林立，车流不息",
            "宁静的湖面，倒映着远处的山脉和蓝天",
            "丰盛的晚餐摆放在餐桌上，有各种美食和饮料",
            "孩子们在公园里玩耍，笑容灿烂，充满活力",
            "书房里，一个人专注地阅读着一本厚厚的书",
            "美丽的日落，天空被染成橙红色，云彩绚丽",
            "现代化的厨房，设备齐全，整洁明亮",
            "花园里盛开的鲜花，色彩斑斓，香气扑鼻",
            "海滩上的日落，海浪轻拍着沙滩，宁静祥和"
        ]
        
    def get_model_config(self) -> Dict:
        """获取当前模型配置"""
        return self.config['models'].get(self.current_model, {})
    
    def get_style_prompt(self) -> str:
        """获取当前风格的提示词"""
        return self.config['description_styles'].get(self.current_style, '')
    
    def generate_caption(self, image_path: str) -> ImageDescription:
        """生成单张图片的描述 - 新增：支持多种模型和风格"""
        max_retries = self.config['max_retries']
        
        for attempt in range(max_retries):
            try:
                model_config = self.get_model_config()
                model_type = model_config.get('type')
                
                if model_type == 'local':
                    return self._generate_local(image_path)
                elif model_type == 'huggingface':
                    return self._generate_with_huggingface(image_path)
                else:
                    raise ValueError(f"不支持的模型类型: {model_type}")
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    time.sleep(wait_time)
                    continue
                else:
                    # 所有重试都失败
                    return ImageDescription(
                        frame_path=image_path,
                        original_description=f"生成失败: {str(e)}",
                        confidence=0.0,
                        language="zh"
                    )
    
    def _generate_local(self, image_path: str) -> ImageDescription:
        """本地测试模式生成 - 新增：用于演示"""
        import random
        
        # 根据图片路径生成一个种子，确保同一张图片的描述一致
        seed = hash(image_path) % len(self.mock_descriptions)
        random.seed(seed)
        
        description = random.choice(self.mock_descriptions)
        
        # 应用风格
        style_prompt = self.get_style_prompt()
        if style_prompt:
            description = self._apply_style_to_description(description, style_prompt)
        
        return ImageDescription(
            frame_path=image_path,
            original_description=description,
            confidence=0.9,
            language="zh"
        )
    
    def _generate_with_huggingface(self, image_path: str) -> ImageDescription:
        """使用Hugging Face API生成描述 - 需要网络连接"""
        model_config = self.get_model_config()
        model_name = model_config['model']
        
        # 对于公开模型，使用推理API
        API_URL = f"https://api-inference.huggingface.co/models/{model_name}"
        
        headers = {"Authorization": f"Bearer {model_config.get('api_key', '')}"} if model_config.get('api_key') else {}
        
        # 准备图片数据
        with open(image_path, "rb") as f:
            data = f.read()
        
        files = {"file": ("image.jpg", data, "image/jpeg")}
        
        try:
            response = requests.post(API_URL, headers=headers, files=files, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                # 解析响应
                if isinstance(result, list) and len(result) > 0:
                    description = result[0].get('generated_text', '')
                elif isinstance(result, dict):
                    description = result.get('generated_text', '')
                else:
                    description = str(result)
                
                # 应用风格
                if description:
                    style_prompt = self.get_style_prompt()
                    description = self._apply_style_to_description(description, style_prompt)
                
                return ImageDescription(
                    frame_path=image_path,
                    original_description=description,
                    confidence=0.8,
                    language="zh"
                )
            else:
                raise Exception(f"API错误: {response.status} - {response.text}")
                
        except Exception as e:
            raise Exception(f"网络请求失败: {str(e)}")
    
    def _apply_style_to_description(self, description: str, style_prompt: str) -> str:
        """应用风格到描述 - 新增：风格化处理"""
        # 简单的风格应用逻辑
        if '简洁' in style_prompt:
            # 提取关键信息
            sentences = description.split('。')
            if sentences:
                return sentences[0].strip() + '。'
        elif '详细' in style_prompt:
            # 确保描述详细
            if len(description) < 50:
                return description + "这张图片包含了丰富的细节，值得仔细观察。"
        elif '场景化' in style_prompt:
            # 添加场景感
            if not any(word in description for word in ['氛围', '环境', '背景']):
                return f"在这个场景中，{description}"
        
        return description


class ImageCaptionApp:
    """图片描述生成GUI应用 - 完整的GUI界面"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("图片描述生成工具")
        self.root.geometry("1200x800")
        
        # 初始化生成器
        self.generator = ImageCaptionGenerator()
        
        # 存储图片和描述
        self.image_files = []
        self.descriptions = []  # List[Tuple[image_path, description]]
        
        # 创建界面
        self.setup_ui()
        
    def setup_ui(self):
        """设置用户界面 - 完整的GUI布局"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # 标题
        title_label = ttk.Label(main_frame, text="图片描述生成工具", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=2, pady=10)
        
        # 左侧控制面板
        control_frame = ttk.LabelFrame(main_frame, text="控制面板", padding="10")
        control_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        
        # 图片上传
        upload_frame = ttk.LabelFrame(control_frame, text="图片上传", padding="5")
        upload_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(upload_frame, text="选择图片", 
                  command=self.select_images).pack(side=tk.LEFT, padx=5)
        ttk.Button(upload_frame, text="选择文件夹", 
                  command=self.select_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(upload_frame, text="清空", 
                  command=self.clear_images).pack(side=tk.LEFT, padx=5)
        
        # 图片预览区
        preview_frame = ttk.LabelFrame(control_frame, text="图片预览", padding="5")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 创建滚动框架
        preview_canvas = tk.Canvas(preview_frame, width=300, height=200)
        scrollbar = ttk.Scrollbar(preview_frame, orient="vertical", command=preview_canvas.yview)
        self.preview_inner = ttk.Frame(preview_canvas)
        
        preview_canvas.configure(yscrollcommand=scrollbar.set)
        preview_canvas_side = preview_canvas.create_window((0, 0), window=self.preview_inner, anchor="nw")
        
        preview_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        def configure_scroll(event):
            size = (self.preview_inner.winfo_reqwidth(), 
                   self.preview_inner.winfo_reqheight())
            preview_canvas.config(scrollregion="0 0 %s %s" % size)
        
        self.preview_inner.bind("<Configure>", configure_scroll)
        
        # 模型选择
        model_frame = ttk.LabelFrame(control_frame, text="模型选择", padding="5")
        model_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.model_var = tk.StringVar(value=self.generator.current_model)
        model_combo = ttk.Combobox(model_frame, textvariable=self.model_var,
                                   values=list(self.generator.config['models'].keys()),
                                   state='readonly', width=25)
        model_combo.pack(pady=5)
        model_combo.bind('<<ComboboxSelected>>', self.on_model_change)
        
        # 描述风格
        style_frame = ttk.LabelFrame(control_frame, text="描述风格", padding="5")
        style_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.style_var = tk.StringVar(value=self.generator.current_style)
        for style in ['简洁', '详细', '场景化']:
            ttk.Radiobutton(style_frame, text=style, variable=self.style_var,
                           value=style, command=self.on_style_change).pack(anchor=tk.W)
        
        # 生成按钮
        self.generate_btn = ttk.Button(control_frame, text="生成描述", 
                                      command=self.generate_descriptions,
                                      style='Accent.TButton')
        self.generate_btn.pack(fill=tk.X, pady=10)
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(control_frame, variable=self.progress_var,
                                          maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        
        self.status_label = ttk.Label(control_frame, text="就绪")
        self.status_label.pack()
        
        # 右侧结果展示区
        result_frame = ttk.LabelFrame(main_frame, text="生成结果", padding="10")
        result_frame.grid(row=1, column=1, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 创建Notebook用于分页显示结果
        self.result_notebook = ttk.Notebook(result_frame)
        self.result_notebook.pack(fill=tk.BOTH, expand=True)
        
        # 底部操作按钮
        action_frame = ttk.Frame(main_frame)
        action_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        ttk.Button(action_frame, text="导出所有描述", 
                  command=self.export_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="复制当前描述", 
                  command=self.copy_current).pack(side=tk.LEFT, padx=5)
        
    def select_images(self):
        """选择图片文件 - 支持多选"""
        filetypes = [
            ("图片文件", "*.jpg *.jpeg *.png *.bmp *.gif"),
            ("所有文件", "*.*")
        ]
        
        files = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=file_types
        )
        
        if files:
            self.add_images(list(files))
    
    def select_folder(self):
        """选择文件夹 - 批量导入"""
        folder = filedialog.askdirectory(title="选择包含图片的文件夹")
        
        if folder:
            # 查找所有图片文件
            image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}
            image_files = []
            
            for file in Path(folder).rglob('*'):
                if file.suffix.lower() in image_extensions:
                    image_files.append(str(file))
            
            if image_files:
                self.add_images(image_files)
            else:
                messagebox.showinfo("提示", "所选文件夹中没有找到图片文件")
    
    def add_images(self, image_paths):
        """添加图片到列表 - 缩略图预览"""
        # 清空现有预览
        for widget in self.preview_inner.winfo_children():
            widget.destroy()
        
        # 添加新图片
        self.image_files = image_paths
        self.descriptions.clear()
        
        # 清空结果
        for tab in self.result_notebook.tabs():
            self.result_notebook.forget(tab)
        
        # 显示缩略图
        for i, image_path in enumerate(image_paths[:10]):  # 最多显示10个预览
            try:
                # 创建缩略图
                img = Image.open(image_path)
                img.thumbnail((80, 80))
                photo = ImageTk.PhotoImage(img)
                
                # 创建预览框架
                preview_item = ttk.Frame(self.preview_inner)
                preview_item.grid(row=i//3, column=i%3, padx=5, pady=5)
                
                # 显示图片
                img_label = ttk.Label(preview_item, image=photo)
                img_label.image = photo  # 保持引用
                img_label.pack()
                
                # 显示文件名
                name_label = ttk.Label(preview_item, 
                                     text=Path(image_path).stem[:10] + '...',
                                     font=('Arial', 8))
                name_label.pack()
                
            except Exception as e:
                print(f"加载图片失败: {image_path} - {e}")
        
        if len(image_paths) > 10:
            count_label = ttk.Label(self.preview_inner, 
                                   text=f"...还有 {len(image_paths)-10} 张图片")
            count_label.grid(row=4, column=0, columnspan=3)
        
        self.update_status(f"已加载 {len(image_paths)} 张图片")
    
    def clear_images(self):
        """清空图片 - 重置功能"""
        self.image_files.clear()
        self.descriptions.clear()
        
        for widget in self.preview_inner.winfo_children():
            widget.destroy()
        
        for tab in self.result_notebook.tabs():
            self.result_notebook.forget(tab)
        
        self.progress_var.set(0)
        self.update_status("就绪")
    
    def on_model_change(self, event=None):
        """模型改变事件 - 动态切换模型"""
        self.generator.current_model = self.model_var.get()
        model_config = self.generator.get_model_config()
        
        # 如果选择了需要API密钥的模型
        if model_config.get('type') == 'huggingface':
            messagebox.showinfo("提示", 
                               f"已切换到 {self.generator.current_model}\n"
                               f"注意：使用此模型需要网络连接")
    
    def on_style_change(self, event=None):
        """风格改变事件 - 动态切换风格"""
        self.generator.current_style = self.style_var.get()
    
    def generate_descriptions(self):
        """生成描述 - 同步处理（简化版）"""
        if not self.image_files:
            messagebox.showwarning("警告", "请先选择图片")
            return
        
        # 禁用按钮
        self.generate_btn.state(['disabled'])
        
        # 在新线程中处理
        threading.Thread(target=self._generate_sync, daemon=True).start()
    
    def _generate_sync(self):
        """同步生成描述 - 简化版本"""
        total = len(self.image_files)
        self.descriptions.clear()
        
        # 清空结果
        self.root.after(0, lambda: [
            self.result_notebook.forget(tab) 
            for tab in self.result_notebook.tabs()
        ])
        
        for i, image_path in enumerate(self.image_files):
            try:
                # 更新进度
                progress = (i / total) * 100
                self.root.after(0, lambda p=progress: self.progress_var.set(p))
                self.root.after(0, lambda c=i, t=total: self.update_status(f"处理中: {c+1}/{t}"))
                
                # 生成描述
                description = self.generator.generate_caption(image_path)
                self.descriptions.append((image_path, description))
                
                # 添加到结果页面
                self.root.after(0, lambda ip=image_path, d=description: self.add_result_tab(ip, d))
                
                # 短暂延迟，避免界面卡顿
                time.sleep(0.1)
                
            except Exception as e:
                error_desc = ImageDescription(
                    frame_path=image_path,
                    original_description=f"生成失败: {str(e)}",
                    confidence=0.0
                )
                self.descriptions.append((image_path, error_desc))
                self.root.after(0, lambda ip=image_path, d=error_desc: self.add_result_tab(ip, d))
        
        # 完成
        self.root.after(0, lambda: [
            self.progress_var.set(100),
            self.update_status(f"生成完成: {total} 张图片"),
            self.generate_btn.state(['!disabled'])
        ])
    
    def add_result_tab(self, image_path, description):
        """添加结果标签页 - 图文并茂的展示"""
        tab_frame = ttk.Frame(self.result_notebook)
        
        # 图片显示
        try:
            img = Image.open(image_path)
            # 限制图片大小
            max_size = (400, 400)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            
            img_label = ttk.Label(tab_frame, image=photo)
            img_label.image = photo  # 保持引用
            img_label.pack(pady=10)
        except Exception as e:
            ttk.Label(tab_frame, text=f"图片加载失败: {e}").pack(pady=10)
        
        # 描述文本
        desc_frame = ttk.LabelFrame(tab_frame, text="生成的描述", padding="10")
        desc_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        desc_text = scrolledtext.ScrolledText(desc_frame, height=8, wrap=tk.WORD)
        desc_text.pack(fill=tk.BOTH, expand=True)
        desc_text.insert('1.0', description.current_description)
        desc_text.config(state='disabled')
        
        # 操作按钮
        button_frame = ttk.Frame(tab_frame)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(button_frame, text="复制描述", 
                  command=lambda: self.copy_to_clipboard(description.current_description)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="编辑描述", 
                  command=lambda: self.edit_description(desc_text, description)).pack(side=tk.LEFT, padx=5)
        
        # 添加标签页
        filename = Path(image_path).stem
        self.result_notebook.add(tab_frame, text=filename[:20])  # 限制标签长度
    
    def edit_description(self, text_widget, description):
        """编辑描述 - 可编辑功能"""
        text_widget.config(state='normal')
        
        def save_edit():
            new_text = text_widget.get('1.0', tk.END).strip()
            description.modified_description = new_text
            text_widget.config(state='disabled')
            save_btn.destroy()
        
        save_btn = ttk.Button(text_widget.master, text="保存", command=save_edit)
        save_btn.pack(side=tk.BOTTOM, pady=5)
    
    def copy_to_clipboard(self, text):
        """复制到剪贴板 - 便捷功能"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("成功", "描述已复制到剪贴板")
    
    def copy_current(self):
        """复制当前描述 - 当前标签页复制"""
        current_tab = self.result_notebook.select()
        if current_tab:
            tab_id = current_tab.split('.')[-1]
            index = self.result_notebook.index(current_tab)
            if index < len(self.descriptions):
                _, description = self.descriptions[index]
                self.copy_to_clipboard(description.current_description)
    
    def export_all(self):
        """导出所有描述 - 批量导出功能"""
        if not self.descriptions:
            messagebox.showwarning("警告", "没有可导出的描述")
            return
        
        # 选择导出格式
        file_types = [
            ("文本文件", "*.txt"),
            ("JSON文件", "*.json"),
            ("所有文件", "*.*")
        ]
        
        file_path = filedialog.asksaveasfilename(
            title="导出描述",
            defaultextension=".txt",
            filetypes=file_types
        )
        
        if file_path:
            try:
                if file_path.endswith('.json'):
                    # JSON格式
                    data = {
                        'total': len(self.descriptions),
                        'export_time': time.time(),
                        'descriptions': [
                            {
                                'image_path': path,
                                'description': desc.current_description,
                                'confidence': desc.confidence
                            }
                            for path, desc in self.descriptions
                        ]
                    }
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                else:
                    # 文本格式
                    with open(file_path, 'w', encoding='utf-8') as f:
                        for i, (image_path, description) in enumerate(self.descriptions, 1):
                            f.write(f"图片 {i}: {Path(image_path).name}\n")
                            f.write(f"描述: {description.current_description}\n")
                            f.write("-" * 50 + "\n")
                
                messagebox.showinfo("成功", f"描述已导出到: {file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {str(e)}")
    
    def update_status(self, message):
        """更新状态标签 - 状态反馈"""
        self.status_label.config(text=message)


def main():
    """主函数 - GUI入口"""
    root = tk.Tk()
    
    # 设置样式
    style = ttk.Style()
    style.theme_use('clam')  # 使用现代主题
    
    # 设置窗口图标和其他属性
    root.resizable(True, True)
    root.minsize(800, 600)
    
    # 创建应用
    app = ImageCaptionApp(root)
    
    # 运行
    root.mainloop()


if __name__ == "__main__":
    main()
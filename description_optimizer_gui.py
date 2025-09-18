#!/usr/bin/env python3
"""
图片描述优化工具 - Tkinter图形界面
基于现有描述生成工具，添加批量修改和单独编辑功能
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import json
import time
from typing import List, Dict, Optional
from description_modifier_enhanced import DescriptionGeneratorStandalone, ImageDescription


class DescriptionOptimizerGUI:
    """描述优化工具图形界面"""
    
    def __init__(self, root: tk.Tk, generator: DescriptionGeneratorStandalone):
        self.root = root
        self.generator = generator
        self.descriptions: List[ImageDescription] = []
        self.selected_indices: List[int] = []
        self.current_video_name: str = ""
        
        self.setup_ui()
        
    def setup_ui(self):
        """设置用户界面"""
        # 设置窗口
        self.root.title("图片描述优化工具")
        self.root.geometry("1200x800")
        
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # === 顶部控制区 ===
        control_frame = ttk.LabelFrame(main_frame, text="控制面板", padding="10")
        control_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 加载描述文件
        ttk.Button(control_frame, text="加载描述文件", 
                  command=self.load_descriptions).grid(row=0, column=0, padx=5)
        
        ttk.Label(control_frame, text="当前视频:").grid(row=0, column=1, padx=5)
        self.video_label = ttk.Label(control_frame, text="未加载", 
                                    font=('Arial', 10, 'bold'))
        self.video_label.grid(row=0, column=2, padx=5)
        
        # === 批量修改区 ===
        batch_frame = ttk.LabelFrame(main_frame, text="批量修改", padding="10")
        batch_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        # 四个修改维度
        dimensions = [
            ("主题:", "theme", "如: 自然风景->城市夜景"),
            ("角色:", "character", "如: 中年男性->年轻女性"),
            ("场景:", "scene", "如: 室内->户外"),
            ("风格:", "style", "如: 写实->赛博朋克")
        ]
        
        self.modify_vars = {}
        for i, (label_text, var_name, placeholder) in enumerate(dimensions):
            ttk.Label(batch_frame, text=label_text).grid(row=i, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar()
            self.modify_vars[var_name] = var
            entry = ttk.Entry(batch_frame, textvariable=var, width=30)
            entry.grid(row=i, column=1, padx=5, pady=2)
            entry.insert(0, placeholder)
            entry.bind("<FocusIn>", lambda e, v=var, p=placeholder: self.clear_placeholder(e, v, p))
            entry.bind("<FocusOut>", lambda e, v=var, p=placeholder: self.restore_placeholder(e, v, p))
        
        # 批量操作按钮
        ttk.Button(batch_frame, text="预览修改", 
                  command=self.preview_batch_modification).grid(row=4, column=0, pady=10)
        ttk.Button(batch_frame, text="应用修改", 
                  command=self.apply_batch_modification).grid(row=4, column=1, pady=10)
        
        # 撤销按钮
        ttk.Button(batch_frame, text="撤销上一步", 
                  command=self.undo_last_modification).grid(row=5, column=0, columnspan=2, pady=5)
        
        # === 描述列表区 ===
        list_frame = ttk.LabelFrame(main_frame, text="描述列表", padding="10")
        list_frame.grid(row=1, column=1, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 创建Treeview
        columns = ('select', 'number', 'description', 'modified')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=25)
        
        # 设置列
        self.tree.heading('select', text='')
        self.tree.heading('number', text='#')
        self.tree.heading('description', text='原始描述')
        self.tree.heading('modified', text='修改后')
        
        self.tree.column('select', width=30, anchor='center')
        self.tree.column('number', width=40, anchor='center')
        self.tree.column('description', width=300, anchor='w')
        self.tree.column('modified', width=300, anchor='w')
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # 绑定双击编辑事件
        self.tree.bind("<Double-1>", self.on_double_click)
        
        # === 底部状态栏 ===
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
        self.status_label = ttk.Label(status_frame, text="就绪")
        self.status_label.grid(row=0, column=0, sticky=tk.W)
        
        ttk.Button(status_frame, text="全选", 
                  command=self.select_all).grid(row=0, column=1, padx=5)
        ttk.Button(status_frame, text="取消全选", 
                  command=self.deselect_all).grid(row=0, column=2, padx=5)
        ttk.Button(status_frame, text="保存", 
                  command=self.save_descriptions).grid(row=0, column=3, padx=5)
        
    def clear_placeholder(self, event, var: tk.StringVar, placeholder: str):
        """清除占位符"""
        if var.get() == placeholder:
            var.set("")
    
    def restore_placeholder(self, event, var: tk.StringVar, placeholder: str):
        """恢复占位符"""
        if not var.get():
            var.set(placeholder)
    
    def load_descriptions(self):
        """加载描述文件"""
        file_path = filedialog.askopenfilename(
            title="选择描述文件",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(self.generator.descriptions_path)
        )
        
        if file_path:
            # 从文件名提取视频名称
            video_name = Path(file_path).stem.replace('_descriptions', '')
            descriptions = self.generator.load_descriptions(video_name)
            
            if descriptions:
                self.descriptions = descriptions
                self.current_video_name = video_name
                self.video_label.config(text=video_name)
                self.update_description_list()
                self.status_label.config(text=f"已加载 {len(descriptions)} 条描述")
            else:
                messagebox.showerror("错误", "加载描述文件失败")
    
    def update_description_list(self):
        """更新描述列表显示"""
        # 清空现有项目
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 添加描述项
        for i, desc in enumerate(self.descriptions):
            values = (
                '',  # 选择框
                str(i + 1),
                desc.original_description[:100] + '...' if len(desc.original_description) > 100 else desc.original_description,
                desc.modified_description[:100] + '...' if len(desc.modified_description) > 100 else desc.modified_description
            )
            item = self.tree.insert('', 'end', values=values)
            
            # 如果有修改历史，标记为已修改
            if desc.modification_history:
                self.tree.item(item, tags=('modified',))
        
        # 设置修改项的样式
        self.tree.tag_configure('modified', background='#e8f5e9')
    
    def on_double_click(self, event):
        """双击编辑单个描述"""
        selection = self.tree.selection()
        if selection:
            item = selection[0]
            index = self.tree.index(item)
            self.edit_single_description(index)
    
    def edit_single_description(self, index: int):
        """编辑单个描述"""
        if 0 <= index < len(self.descriptions):
            desc = self.descriptions[index]
            
            # 创建编辑窗口
            edit_window = tk.Toplevel(self.root)
            edit_window.title(f"编辑描述 #{index + 1}")
            edit_window.geometry("600x400")
            
            # 原始描述
            ttk.Label(edit_window, text="原始描述:", font=('Arial', 10, 'bold')).grid(
                row=0, column=0, sticky=tk.W, padx=10, pady=5)
            original_text = scrolledtext.ScrolledText(edit_window, height=5, width=60)
            original_text.grid(row=1, column=0, columnspan=2, padx=10, pady=5)
            original_text.insert('1.0', desc.original_description)
            original_text.config(state='disabled')
            
            # 修改后的描述
            ttk.Label(edit_window, text="修改后的描述:", font=('Arial', 10, 'bold')).grid(
                row=2, column=0, sticky=tk.W, padx=10, pady=5)
            modified_text = scrolledtext.ScrolledText(edit_window, height=5, width=60)
            modified_text.grid(row=3, column=0, columnspan=2, padx=10, pady=5)
            modified_text.insert('1.0', desc.current_description)
            
            # 修改规则
            ttk.Label(edit_window, text="修改规则 (每行一个，格式: 旧词->新词):").grid(
                row=4, column=0, sticky=tk.W, padx=10, pady=5)
            rules_text = scrolledtext.ScrolledText(edit_window, height=5, width=60)
            rules_text.grid(row=5, column=0, columnspan=2, padx=10, pady=5)
            
            # 按钮
            button_frame = ttk.Frame(edit_window)
            button_frame.grid(row=6, column=0, columnspan=2, pady=10)
            
            def apply_changes():
                # 获取修改规则
                rules_text_content = rules_text.get('1.0', tk.END).strip()
                modifications = {}
                
                if rules_text_content:
                    for line in rules_text_content.split('\n'):
                        if '->' in line:
                            old, new = line.split('->', 1)
                            modifications[old.strip()] = new.strip()
                
                if modifications:
                    # 应用修改
                    modified_desc = self.generator.apply_single_modification(desc, modifications)
                    self.descriptions[index] = modified_desc
                    
                    # 更新显示
                    modified_text.delete('1.0', tk.END)
                    modified_text.insert('1.0', modified_desc.current_description)
                    
                    self.update_description_list()
                    messagebox.showinfo("成功", "修改已应用")
                else:
                    messagebox.showwarning("警告", "请输入有效的修改规则")
            
            ttk.Button(button_frame, text="应用修改", 
                      command=apply_changes).grid(row=0, column=0, padx=5)
            ttk.Button(button_frame, text="关闭", 
                      command=edit_window.destroy).grid(row=0, column=1, padx=5)
    
    def select_all(self):
        """全选"""
        for item in self.tree.get_children():
            self.tree.set(item, 'select', '✓')
    
    def deselect_all(self):
        """取消全选"""
        for item in self.tree.get_children():
            self.tree.set(item, 'select', '')
    
    def preview_batch_modification(self):
        """预览批量修改"""
        if not self.descriptions:
            messagebox.showwarning("警告", "请先加载描述文件")
            return
        
        # 获取选中的项目
        selected_indices = self.get_selected_indices()
        if not selected_indices:
            messagebox.showwarning("警告", "请选择要修改的描述")
            return
        
        # 创建修改规则
        modifications = self.create_modifications_from_ui()
        if not modifications:
            messagebox.showwarning("警告", "请输入修改规则")
            return
        
        # 显示预览窗口
        preview_window = tk.Toplevel(self.root)
        preview_window.title("批量修改预览")
        preview_window.geometry("800x600")
        
        # 创建预览文本框
        preview_text = scrolledtext.ScrolledText(preview_window, height=25, width=80)
        preview_text.grid(row=0, column=0, padx=10, pady=10, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        preview_window.columnconfigure(0, weight=1)
        preview_window.rowconfigure(0, weight=1)
        
        # 生成预览内容
        previews = self.generator.show_modification_preview(
            self.descriptions, modifications, selected_indices
        )
        
        preview_content = "=== 批量修改预览 ===\n\n"
        for i, (original, modified) in enumerate(previews, 1):
            preview_content += f"修改 {i}:\n"
            preview_content += f"原: {original}\n"
            preview_content += f"新: {modified}\n"
            preview_content += "-" * 60 + "\n\n"
        
        preview_text.insert('1.0', preview_content)
        preview_text.config(state='disabled')
        
        # 关闭按钮
        ttk.Button(preview_window, text="关闭", 
                  command=preview_window.destroy).grid(row=1, column=0, pady=5)
    
    def apply_batch_modification(self):
        """应用批量修改"""
        if not self.descriptions:
            messagebox.showwarning("警告", "请先加载描述文件")
            return
        
        # 获取选中的项目
        selected_indices = self.get_selected_indices()
        if not selected_indices:
            if not messagebox.askyesno("提示", "未选择任何描述，是否应用到全部？"):
                return
            selected_indices = None
        
        # 创建修改规则
        modifications = self.create_modifications_from_ui()
        if not modifications:
            messagebox.showwarning("警告", "请输入修改规则")
            return
        
        # 确认修改
        if not messagebox.askyesno("确认", f"确定要应用 {len(modifications)} 个修改规则吗？"):
            return
        
        # 应用修改
        modified_descriptions = self.generator.apply_batch_modifications(
            self.descriptions, modifications, selected_indices
        )
        
        self.descriptions = modified_descriptions
        self.update_description_list()
        
        # 统计修改数量
        changes_count = sum(1 for i, desc in enumerate(self.descriptions)
                          if desc.current_description != self.descriptions[i].current_description)
        self.status_label.config(text=f"已修改 {changes_count} 条描述")
        
        messagebox.showinfo("成功", f"批量修改完成，共修改 {changes_count} 条描述")
    
    def undo_last_modification(self):
        """撤销最后一次修改"""
        if not self.descriptions:
            messagebox.showwarning("警告", "没有可撤销的描述")
            return
        
        # 检查是否有修改历史
        has_history = any(desc.modification_history for desc in self.descriptions)
        if not has_history:
            messagebox.showinfo("提示", "没有可撤销的修改历史")
            return
        
        # 确认撤销
        if messagebox.askyesno("确认", "确定要撤销最后一次修改吗？"):
            restored_descriptions = self.generator.undo_modifications(self.descriptions, 1)
            self.descriptions = restored_descriptions
            self.update_description_list()
            self.status_label.config(text="已撤销最后一次修改")
    
    def get_selected_indices(self) -> List[int]:
        """获取选中的描述索引"""
        selected = []
        for item in self.tree.get_children():
            if self.tree.item(item)['values'][0] == '✓':
                selected.append(self.tree.index(item))
        return selected
    
    def create_modifications_from_ui(self) -> Dict[str, str]:
        """从UI创建修改规则"""
        modifications = {}
        
        # 获取各个维度的修改规则
        theme = self.modify_vars['theme'].get()
        character = self.modify_vars['character'].get()
        scene = self.modify_vars['scene'].get()
        style = self.modify_vars['style'].get()
        
        # 过滤掉占位符
        placeholders = {
            "如: 自然风景->城市夜景",
            "如: 中年男性->年轻女性", 
            "如: 室内->户外",
            "如: 写实->赛博朋克"
        }
        
        if theme and theme not in placeholders.values():
            if '->' in theme:
                old, new = theme.split('->', 1)
                modifications[old.strip()] = new.strip()
        
        if character and character not in placeholders.values():
            if '->' in character:
                old, new = character.split('->', 1)
                modifications[old.strip()] = new.strip()
        
        if scene and scene not in placeholders.values():
            if '->' in scene:
                old, new = scene.split('->', 1)
                modifications[old.strip()] = new.strip()
        
        if style and style not in placeholders.values():
            if '->' in style:
                old, new = style.split('->', 1)
                modifications[old.strip()] = new.strip()
        
        return modifications
    
    def save_descriptions(self):
        """保存描述"""
        if not self.descriptions:
            messagebox.showwarning("警告", "没有可保存的描述")
            return
        
        # 询问保存文件名
        default_name = f"{self.current_video_name}_optimized"
        file_path = filedialog.asksaveasfilename(
            title="保存描述",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(self.generator.descriptions_path)
        )
        
        if file_path:
            video_name = Path(file_path).stem.replace('_descriptions', '')
            save_path = self.generator.save_descriptions(self.descriptions, video_name)
            
            if save_path:
                messagebox.showinfo("成功", f"描述已保存到: {save_path}")
                self.status_label.config(text=f"已保存: {video_name}")
            else:
                messagebox.showerror("错误", "保存失败")


def main():
    """主函数"""
    # 创建生成器实例
    config = {
        'descriptions_path': 'generated_descriptions',
        'test_mode': True,
        'max_concurrent': 2
    }
    
    generator = DescriptionGeneratorStandalone(config)
    
    # 创建GUI窗口
    root = tk.Tk()
    app = DescriptionOptimizerGUI(root, generator)
    
    # 运行应用
    root.mainloop()


if __name__ == "__main__":
    main()
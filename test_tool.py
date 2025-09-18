#!/usr/bin/env python3
"""
测试脚本 - 验证图片描述生成工具的基本功能
"""

import sys
import os
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # 导入必要的模块
    from PIL import Image
    print("✅ PIL/Pillow 导入成功")
    
    # 导入主模块
    from image_caption_tool_simple import ImageCaptionGenerator, ImageDescription
    print("✅ 主模块导入成功")
    
    # 测试生成器初始化
    generator = ImageCaptionGenerator()
    print("✅ 生成器初始化成功")
    
    # 测试模型配置
    print(f"✅ 当前模型: {generator.current_model}")
    print(f"✅ 可用模型: {list(generator.config['models'].keys())}")
    
    # 测试风格配置
    print(f"✅ 当前风格: {generator.current_style}")
    print(f"✅ 可用风格: {list(generator.config['description_styles'].keys())}")
    
    # 测试描述生成（使用模拟路径）
    test_path = "/tmp/test_image.jpg"
    description = generator.generate_caption(test_path)
    print(f"✅ 描述生成成功: {description.original_description[:50]}...")
    
    # 测试数据类
    desc = ImageDescription(
        frame_path="/tmp/test.jpg",
        original_description="这是一张测试图片",
        confidence=0.9
    )
    print(f"✅ 数据类创建成功: {desc.current_description}")
    
    print("\n🎉 所有基本功能测试通过！")
    print("\n要运行GUI程序，请执行:")
    print("python3 image_caption_tool_simple.py")
    
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("请确保安装了必要的依赖:")
    print("pip3 install pillow requests")
    
except Exception as e:
    print(f"❌ 测试失败: {e}")
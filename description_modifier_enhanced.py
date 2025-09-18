#!/usr/bin/env python3
"""
图片描述生成与微调独立模块
使用AI模型为提取的帧生成描述，支持批量修改和单独调整
可独立运行，包含模拟API和测试数据
"""

import asyncio
import json
import os
import time
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from PIL import Image
import aiohttp
import requests


@dataclass
class ImageDescription:
    """图片描述数据类"""
    frame_path: str
    original_description: str
    modified_description: str = ""
    timestamp: float = 0.0
    frame_number: int = 0
    confidence: float = 0.0
    language: str = "zh"  # zh/en
    tags: List[str] = None
    modification_history: List[Dict] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.modification_history is None:
            self.modification_history = []
        if not self.modified_description:
            self.modified_description = self.original_description

    @property
    def current_description(self) -> str:
        """获取当前描述（优先使用修改后的）"""
        return self.modified_description or self.original_description


class DescriptionGeneratorStandalone:
    """图片描述生成器独立版本"""

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化描述生成器

        Args:
            config: 配置字典，如果为None则使用默认配置
        """
        # 默认配置
        self.default_config = {
            'descriptions_path': 'descriptions',
            'test_mode': True,  # 默认使用测试模式
            'max_concurrent': 3,
            'api_timeout': 30,
            'max_retries': 3,
            'description_prompt': self._get_default_prompt(),
            'translation_prompt': self._get_default_translation_prompt(),
            'apis': {
                'groq': {
                    'api_key': '',
                    'base_url': 'https://api.groq.com/openai/v1',
                    'model': 'llama3-8b-8192'
                },
                'huggingface': {
                    'api_key': '',
                    'base_url': 'https://api-inference.huggingface.co',
                    'model': 'microsoft/DialoGPT-large'
                }
            }
        }

        # 合并用户配置
        self.config = {**self.default_config, **(config or {})}

        # 设置描述保存路径
        self.descriptions_path = Path(self.config['descriptions_path'])
        self.descriptions_path.mkdir(parents=True, exist_ok=True)

        print(f"✅ 描述生成器初始化完成")
        print(f"📁 描述保存目录: {self.descriptions_path}")
        print(f"🔧 模式: {'测试模式' if self.config['test_mode'] else '实际API模式'}")

    def _get_default_prompt(self) -> str:
        """获取默认描述提示词"""
        return """请详细描述这张图片中的内容，包括：
1. 主要物体或人物
2. 场景和背景
3. 颜色和光线
4. 动作或表情
5. 整体氛围
请用生动的语言，控制在100字以内。"""

    def _get_default_translation_prompt(self) -> str:
        """获取默认翻译提示词"""
        return """Please translate the following Chinese description to English,
keeping it suitable for AI image generation:"""

    async def generate_descriptions_batch(self, frames: List[Dict]) -> List[ImageDescription]:
        """
        批量生成图片描述

        Args:
            frames: 帧信息列表，格式：[{'path': '图片路径', 'timestamp': 时间戳, ...}]

        Returns:
            描述列表
        """
        descriptions = []
        total_frames = len(frames)

        print(f"🚀 开始批量生成描述: {total_frames} 张图片")

        if self.config['test_mode']:
            # 测试模式：使用模拟描述
            for i, frame_info in enumerate(frames):
                description = self._generate_mock_description(frame_info, i)
                descriptions.append(description)

                if (i + 1) % 5 == 0 or (i + 1) == total_frames:
                    print(f"📝 已生成: {i + 1}/{total_frames} 个描述")

        else:
            # 实际API模式：并发调用
            semaphore = asyncio.Semaphore(self.config['max_concurrent'])

            async def process_frame(frame_info: Dict, index: int) -> ImageDescription:
                async with semaphore:
                    try:
                        description = await self.generate_single_description(frame_info)

                        if (index + 1) % 5 == 0 or (index + 1) == total_frames:
                            print(f"📝 已生成: {index + 1}/{total_frames} 个描述")

                        return description

                    except Exception as e:
                        print(f"⚠️  生成描述失败: {frame_info.get('path', '')} - {e}")
                        return ImageDescription(
                            frame_path=frame_info.get('path', ''),
                            original_description=f"生成失败: {str(e)}",
                            timestamp=frame_info.get('timestamp', 0),
                            frame_number=index
                        )

            # 并行处理所有帧
            tasks = [process_frame(frame, i) for i, frame in enumerate(frames)]
            descriptions = await asyncio.gather(*tasks, return_exceptions=True)

            # 过滤异常结果
            descriptions = [d for d in descriptions if isinstance(d, ImageDescription)]

        print(f"✅ 描述生成完成: {len(descriptions)}/{total_frames}")
        return descriptions

    async def generate_single_description(self, frame_info: Dict) -> ImageDescription:
        """
        生成单张图片描述

        Args:
            frame_info: 帧信息字典

        Returns:
            图片描述对象
        """
        frame_path = frame_info.get('path', '')

        if self.config['test_mode']:
            return self._generate_mock_description(frame_info, 0)

        try:
            # 准备提示词
            prompt = self._prepare_description_prompt(frame_info)

            # 尝试不同的API提供商
            for provider in ['groq', 'huggingface']:
                try:
                    response = await self._call_text_api(prompt, provider)
                    if response['success']:
                        description_text = self._extract_description_text(response['data'])

                        return ImageDescription(
                            frame_path=frame_path,
                            original_description=description_text,
                            timestamp=frame_info.get('timestamp', 0),
                            frame_number=frame_info.get('frame_number', 0),
                            confidence=0.8,
                            language="zh"
                        )
                except Exception as e:
                    print(f"⚠️  API {provider} 失败: {e}")
                    continue

            # 所有API都失败，返回基础描述
            return ImageDescription(
                frame_path=frame_path,
                original_description=f"一张视频帧图片 (时间: {frame_info.get('timestamp', 0):.1f}s)",
                timestamp=frame_info.get('timestamp', 0),
                frame_number=frame_info.get('frame_number', 0),
                confidence=0.1
            )

        except Exception as e:
            print(f"❌ 生成描述失败: {frame_path} - {e}")
            return ImageDescription(
                frame_path=frame_path,
                original_description=f"描述生成失败: {str(e)}",
                timestamp=frame_info.get('timestamp', 0),
                frame_number=frame_info.get('frame_number', 0),
                confidence=0.0
            )

    def _prepare_description_prompt(self, frame_info: Dict) -> str:
        """准备描述提示词"""
        prompt = self.config['description_prompt']

        # 添加上下文信息
        context = f"\n\n图片信息:\n"
        context += f"- 时间戳: {frame_info.get('timestamp', 0):.1f}秒\n"
        context += f"- 帧序号: {frame_info.get('frame_number', 0)}\n"

        if 'dimensions' in frame_info:
            width, height = frame_info['dimensions']
            context += f"- 尺寸: {width}x{height}\n"

        return prompt + context

    async def _call_text_api(self, prompt: str, provider: str) -> Dict:
        """调用文本生成API"""
        api_config = self.config['apis'].get(provider, {})

        if not api_config.get('api_key') and provider != 'huggingface':
            return {'success': False, 'error': f'{provider} API密钥未配置'}

        try:
            if provider == 'groq':
                return await self._call_groq_api(prompt, api_config)
            elif provider == 'huggingface':
                return await self._call_huggingface_api(prompt, api_config)
            else:
                return {'success': False, 'error': f'不支持的提供商: {provider}'}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def _call_groq_api(self, prompt: str, config: Dict) -> Dict:
        """调用Groq API"""
        url = f"{config['base_url']}/chat/completions"

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json"
        }

        data = {
            "model": config['model'],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "temperature": 0.7
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=self.config['api_timeout']) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    content = result["choices"][0]["message"]["content"]
                    return {'success': True, 'data': content}
                else:
                    error_text = await resp.text()
                    return {'success': False, 'error': f"Groq API错误: {resp.status} - {error_text}"}

    async def _call_huggingface_api(self, prompt: str, config: Dict) -> Dict:
        """调用Hugging Face API"""
        model = config.get('model', 'microsoft/DialoGPT-large')
        url = f"{config['base_url']}/models/{model}"

        headers = {"Content-Type": "application/json"}
        if config.get('api_key'):
            headers["Authorization"] = f"Bearer {config['api_key']}"

        data = {
            "inputs": prompt,
            "parameters": {
                "max_length": 200,
                "temperature": 0.7
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=self.config['api_timeout']) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if isinstance(result, list) and result:
                        content = result[0].get("generated_text", "")
                    else:
                        content = str(result)
                    return {'success': True, 'data': content}
                else:
                    error_text = await resp.text()
                    return {'success': False, 'error': f"Hugging Face API错误: {resp.status} - {error_text}"}

    def _extract_description_text(self, response_text: str) -> str:
        """从AI响应中提取描述文本"""
        text = response_text.strip()

        # 如果响应包含JSON，尝试解析
        try:
            if text.startswith('{') and text.endswith('}'):
                data = json.loads(text)
                if 'description' in data:
                    return data['description']
                elif 'content' in data:
                    return data['content']
        except json.JSONDecodeError:
            pass

        # 移除常见的前缀
        prefixes_to_remove = [
            "这张图片显示", "图片中", "在这张图片中", "这是一张",
            "描述:", "Description:", "图片描述:", "内容:"
        ]

        for prefix in prefixes_to_remove:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()

        return text[:200]  # 限制长度

    def _generate_mock_description(self, frame_info: Dict, index: int) -> ImageDescription:
        """生成模拟描述（测试模式）"""
        timestamp = frame_info.get('timestamp', 0)
        frame_number = frame_info.get('frame_number', index)

        mock_descriptions = [
            f"一个人物站在室内场景中，光线柔和，背景温馨 (第{frame_number}帧)",
            f"户外自然风景，绿色植物和蓝天背景，阳光明媚 (时间{timestamp:.1f}s)",
            f"室内对话场景，两人面对面交谈，温暖的灯光氛围",
            f"动作场面，人物快速移动，画面动感十足",
            f"静物特写，物品细节清晰可见，构图精美",
            f"城市街景，车水马龙，现代都市风貌",
            f"夜晚场景，灯光璀璨，营造浪漫氛围",
            f"食物特写，色彩丰富，令人食欲大增",
            f"动物画面，生动活泼，自然和谐",
            f"风景如画，山水相依，意境深远"
        ]

        description_text = mock_descriptions[frame_number % len(mock_descriptions)]

        return ImageDescription(
            frame_path=frame_info.get('path', ''),
            original_description=description_text,
            timestamp=timestamp,
            frame_number=frame_number,
            confidence=0.9,
            language="zh",
            tags=["测试", "模拟"]
        )

    async def translate_descriptions(self, descriptions: List[ImageDescription],
                                   target_language: str = "en") -> List[ImageDescription]:
        """
        翻译描述

        Args:
            descriptions: 描述列表
            target_language: 目标语言

        Returns:
            翻译后的描述列表
        """
        if target_language == "zh":
            return descriptions  # 已经是中文，无需翻译

        print(f"🌐 开始翻译描述: {len(descriptions)} 条 -> {target_language}")

        translated_descriptions = []

        for i, desc in enumerate(descriptions):
            try:
                if self.config['test_mode']:
                    # 模拟翻译
                    translated_text = f"[EN] {desc.current_description}"
                else:
                    # 实际翻译API调用
                    prompt = f"{self.config['translation_prompt']}\n\n{desc.current_description}"

                    # 尝试翻译API
                    response = await self._call_text_api(prompt, 'groq')
                    if response['success']:
                        translated_text = response['data'].strip()
                    else:
                        translated_text = f"[Translation failed] {desc.current_description}"

                # 创建新的描述对象
                translated_desc = ImageDescription(
                    frame_path=desc.frame_path,
                    original_description=desc.original_description,
                    modified_description=translated_text,
                    timestamp=desc.timestamp,
                    frame_number=desc.frame_number,
                    confidence=desc.confidence,
                    language=target_language,
                    tags=desc.tags.copy(),
                    modification_history=desc.modification_history.copy()
                )

                translated_descriptions.append(translated_desc)

                if (i + 1) % 10 == 0 or (i + 1) == len(descriptions):
                    print(f"🌐 翻译进度: {i + 1}/{len(descriptions)}")

            except Exception as e:
                print(f"⚠️  翻译失败: {e}")
                translated_descriptions.append(desc)  # 保持原描述

        print(f"✅ 翻译完成: {len(translated_descriptions)} 条")
        return translated_descriptions

    def create_modify_rules(self, theme: str = None, character: str = None,
                          scene: str = None, style: str = None) -> Dict[str, str]:
        """
        创建描述修改规则

        Args:
            theme: 主题修改规则，如 "自然风景->城市夜景"
            character: 角色修改规则，如 "中年男性->年轻女性"
            scene: 场景修改规则，如 "室内->户外"
            style: 风格修改规则，如 "写实风格->赛博朋克风格"

        Returns:
            修改规则字典
        """
        rules = {}

        # 处理主题规则
        if theme:
            if '->' in theme:
                old_theme, new_theme = theme.split('->', 1)
                rules[old_theme.strip()] = new_theme.strip()

        # 处理角色规则
        if character:
            if '->' in character:
                old_char, new_char = character.split('->', 1)
                rules[old_char.strip()] = new_char.strip()

        # 处理场景规则
        if scene:
            if '->' in scene:
                old_scene, new_scene = scene.split('->', 1)
                rules[old_scene.strip()] = new_scene.strip()

        # 处理风格规则
        if style:
            if '->' in style:
                old_style, new_style = style.split('->', 1)
                rules[old_style.strip()] = new_style.strip()

        return rules

    def smart_text_replace(self, text: str, old_word: str, new_word: str,
                          language: str = "zh") -> str:
        """
        智能文本替换，考虑语法和语境

        Args:
            text: 原始文本
            old_word: 要替换的词
            new_word: 新词
            language: 语言类型

        Returns:
            替换后的文本
        """
        if not old_word or not new_word:
            return text

        # 使用正则表达式进行智能匹配
        pattern = re.compile(r'\b' + re.escape(old_word) + r'\b', re.IGNORECASE)

        # 执行替换
        result = pattern.sub(new_word, text)

        # 特殊处理中文
        if language == "zh":
            # 中文没有空格分隔，需要额外处理
            result = result.replace(old_word, new_word)

        return result

    def apply_batch_modifications(self, descriptions: List[ImageDescription],
                                modifications: Dict[str, str],
                                selected_indices: List[int] = None) -> List[ImageDescription]:
        """
        批量修改描述，支持选择性修改

        Args:
            descriptions: 描述列表
            modifications: 修改规则字典
            selected_indices: 选中的描述索引列表，None表示全部修改

        Returns:
            修改后的描述列表
        """
        print(f"✏️  开始批量修改: {len(modifications)} 个规则应用到 "
              f"{len(selected_indices) if selected_indices else len(descriptions)} 条描述")

        modified_descriptions = []

        for i, desc in enumerate(descriptions):
            # 如果指定了选中索引且当前不在选中范围内，跳过
            if selected_indices is not None and i not in selected_indices:
                modified_descriptions.append(desc)
                continue

            current_text = desc.current_description
            modified_text = current_text

            # 记录修改历史
            changes = []

            # 应用所有修改规则
            for old_text, new_text in modifications.items():
                if old_text in current_text:
                    modified_text = self.smart_text_replace(
                        modified_text, old_text, new_text, desc.language
                    )
                    changes.append({
                        'type': 'batch',
                        'from': old_text,
                        'to': new_text,
                        'timestamp': time.time()
                    })

            # 创建新的描述对象
            modified_desc = ImageDescription(
                frame_path=desc.frame_path,
                original_description=desc.original_description,
                modified_description=modified_text,
                timestamp=desc.timestamp,
                frame_number=desc.frame_number,
                confidence=desc.confidence,
                language=desc.language,
                tags=desc.tags.copy(),
                modification_history=desc.modification_history.copy() + changes[-3:]  # 只保留最近3次
            )

            modified_descriptions.append(modified_desc)

        changes_count = sum(1 for i, desc in enumerate(modified_descriptions)
                          if desc.current_description != descriptions[i].current_description)

        print(f"✅ 批量修改完成: {changes_count} 条描述被修改")
        return modified_descriptions

    def apply_single_modification(self, description: ImageDescription,
                                 modifications: Dict[str, str]) -> ImageDescription:
        """
        单独修改一条描述

        Args:
            description: 单个描述对象
            modifications: 修改规则字典

        Returns:
            修改后的描述对象
        """
        current_text = description.current_description
        modified_text = current_text

        # 记录修改历史
        changes = []

        # 应用所有修改规则
        for old_text, new_text in modifications.items():
            if old_text in current_text:
                modified_text = self.smart_text_replace(
                    modified_text, old_text, new_text, description.language
                )
                changes.append({
                    'type': 'single',
                    'from': old_text,
                    'to': new_text,
                    'timestamp': time.time()
                })

        # 创建新的描述对象
        modified_desc = ImageDescription(
            frame_path=description.frame_path,
            original_description=description.original_description,
            modified_description=modified_text,
            timestamp=description.timestamp,
            frame_number=description.frame_number,
            confidence=description.confidence,
            language=description.language,
            tags=description.tags.copy(),
            modification_history=description.modification_history.copy() + changes[-3:]
        )

        return modified_desc

    def undo_modifications(self, descriptions: List[ImageDescription],
                          steps: int = 1) -> List[ImageDescription]:
        """
        撤销修改操作

        Args:
            descriptions: 描述列表
            steps: 撤销的步数

        Returns:
            撤销后的描述列表
        """
        restored_descriptions = []

        for desc in descriptions:
            if not desc.modification_history:
                restored_descriptions.append(desc)
                continue

            # 获取需要撤销的修改
            history = desc.modification_history
            if len(history) < steps:
                steps = len(history)

            # 从最后开始撤销
            current_text = desc.current_description
            for i in range(min(steps, len(history))):
                change = history[-(i+1)]
                # 撤销替换
                current_text = self.smart_text_replace(
                    current_text, change['to'], change['from'], desc.language
                )

            # 创建恢复的描述对象
            restored_desc = ImageDescription(
                frame_path=desc.frame_path,
                original_description=desc.original_description,
                modified_description=current_text,
                timestamp=desc.timestamp,
                frame_number=desc.frame_number,
                confidence=desc.confidence,
                language=desc.language,
                tags=desc.tags.copy(),
                modification_history=history[:-steps] if steps > 0 else history
            )

            restored_descriptions.append(restored_desc)

        print(f"↩️  撤销完成: {steps} 步操作已恢复")
        return restored_descriptions

    def save_descriptions(self, descriptions: List[ImageDescription],
                         video_name: str) -> str:
        """
        保存描述到文件

        Args:
            descriptions: 描述列表
            video_name: 视频名称

        Returns:
            保存文件路径
        """
        try:
            # 创建保存路径
            save_path = self.descriptions_path / f"{video_name}_descriptions.json"

            # 转换为可序列化的字典
            data = {
                'video_name': video_name,
                'total_descriptions': len(descriptions),
                'created_at': time.time(),
                'config': self.config,
                'descriptions': [asdict(desc) for desc in descriptions]
            }

            # 保存到JSON文件
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)

            print(f"💾 描述已保存: {save_path}")
            return str(save_path)

        except Exception as e:
            print(f"❌ 保存描述失败: {e}")
            return ""

    def load_descriptions(self, video_name: str) -> List[ImageDescription]:
        """
        从文件加载描述

        Args:
            video_name: 视频名称

        Returns:
            描述列表
        """
        try:
            load_path = self.descriptions_path / f"{video_name}_descriptions.json"

            if not load_path.exists():
                print(f"⚠️  描述文件不存在: {load_path}")
                return []

            with open(load_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            descriptions = []
            for desc_data in data.get('descriptions', []):
                desc = ImageDescription(**desc_data)
                descriptions.append(desc)

            print(f"📖 描述已加载: {len(descriptions)} 条")
            return descriptions

        except Exception as e:
            print(f"❌ 加载描述失败: {e}")
            return []

    def create_test_frames(self, count: int = 10) -> List[Dict]:
        """
        创建测试用的帧信息

        Args:
            count: 创建数量

        Returns:
            帧信息列表
        """
        test_frames = []

        for i in range(count):
            frame_info = {
                'path': f'test_frame_{i:03d}.jpg',
                'timestamp': i * 2.5,  # 每2.5秒一帧
                'frame_number': i,
                'dimensions': (640, 480),
                'size': 1024 * 50  # 模拟50KB
            }
            test_frames.append(frame_info)

        print(f"🧪 创建测试帧信息: {count} 条")
        return test_frames

    def show_modification_preview(self, descriptions: List[ImageDescription],
                                 modifications: Dict[str, str],
                                 selected_indices: List[int] = None) -> List[Tuple[str, str]]:
        """
        显示修改预览

        Args:
            descriptions: 描述列表
            modifications: 修改规则
            selected_indices: 选中的索引

        Returns:
            修改前后的文本对列表
        """
        previews = []

        for i, desc in enumerate(descriptions):
            if selected_indices is not None and i not in selected_indices:
                continue

            original = desc.current_description
            modified = original

            for old_text, new_text in modifications.items():
                modified = self.smart_text_replace(
                    modified, old_text, new_text, desc.language
                )

            if modified != original:
                previews.append((original, modified))

        return previews


def main():
    """主函数 - 独立运行示例"""
    print("=" * 60)
    print("📝 图片描述生成与微调独立模块")
    print("=" * 60)

    # 创建描述生成器实例
    config = {
        'descriptions_path': 'generated_descriptions',
        'test_mode': True,  # 使用测试模式
        'max_concurrent': 2
    }

    generator = DescriptionGeneratorStandalone(config)

    # 选择测试模式
    print("\n请选择运行模式:")
    print("1. 使用测试帧数据生成描述")
    print("2. 从JSON文件加载帧信息并生成描述")
    print("3. 批量修改已有描述（新功能）")
    print("4. 单独修改描述（新功能）")
    print("5. 撤销修改操作（新功能）")
    print("6. 翻译描述")
    print("7. 查看已保存的描述")

    choice = input("\n请输入选择 (1-7): ").strip()

    if choice == "1":
        # 使用测试数据
        frame_count = int(input("请输入测试帧数量 (默认10): ").strip() or "10")
        test_frames = generator.create_test_frames(frame_count)

        print(f"\n🚀 开始生成 {len(test_frames)} 个描述...")
        descriptions = asyncio.run(generator.generate_descriptions_batch(test_frames))

        # 显示结果
        print(f"\n📝 生成的描述:")
        for i, desc in enumerate(descriptions[:5]):  # 只显示前5个
            print(f"{i+1}. {desc.current_description}")

        if len(descriptions) > 5:
            print(f"... 还有 {len(descriptions)-5} 个描述")

        # 保存结果
        video_name = input("\n请输入视频名称 (用于保存): ").strip() or "test_video"
        save_path = generator.save_descriptions(descriptions, video_name)

    elif choice == "2":
        # 从JSON文件加载
        json_path = input("请输入帧信息JSON文件路径: ").strip()
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 提取帧信息
                frames = []
                if 'results' in data:  # 来自帧提取模块的结果
                    for result in data['results']:
                        if result.get('success') and 'frames' in result:
                            frames.extend(result['frames'])
                elif isinstance(data, list):  # 直接的帧列表
                    frames = data

                if frames:
                    print(f"📋 加载到 {len(frames)} 个帧信息")
                    descriptions = asyncio.run(generator.generate_descriptions_batch(frames))

                    video_name = input("请输入视频名称 (用于保存): ").strip() or "loaded_video"
                    generator.save_descriptions(descriptions, video_name)
                else:
                    print("❌ 未找到有效的帧信息")

            except Exception as e:
                print(f"❌ 加载JSON文件失败: {e}")
        else:
            print("❌ 文件不存在")

    elif choice == "3":
        # 批量修改（新功能）
        video_name = input("请输入要修改的视频名称: ").strip()
        descriptions = generator.load_descriptions(video_name)

        if descriptions:
            print(f"\n📋 加载到 {len(descriptions)} 条描述")
            print("\n=== 批量修改模式 ===")

            # 显示描述列表供选择
            print("\n可用的描述:")
            for i, desc in enumerate(descriptions):
                print(f"{i+1}. {desc.current_description[:50]}...")

            # 选择要修改的描述
            selection = input("\n请输入要修改的描述编号 (如: 1,3,5 或 all): ").strip()
            if selection.lower() == "all":
                selected_indices = None
            else:
                selected_indices = [int(x.strip())-1 for x in selection.split(',')]

            # 输入修改规则
            print("\n请输入修改规则 (4个维度独立设置):")
            theme = input("主题修改 (如: 自然风景->城市夜景，回车跳过): ").strip()
            character = input("角色修改 (如: 中年男性->年轻女性，回车跳过): ").strip()
            scene = input("场景修改 (如: 室内->户外，回车跳过): ").strip()
            style = input("风格修改 (如: 写实->赛博朋克，回车跳过): ").strip()

            # 创建修改规则
            modifications = generator.create_modify_rules(
                theme=theme if theme else None,
                character=character if character else None,
                scene=scene if scene else None,
                style=style if style else None
            )

            if modifications:
                # 显示预览
                print("\n=== 修改预览 ===")
                previews = generator.show_modification_preview(
                    descriptions, modifications, selected_indices
                )
                for original, modified in previews[:5]:  # 只显示前5个预览
                    print(f"原: {original[:50]}...")
                    print(f"新: {modified[:50]}...")
                    print("-" * 40)

                if len(previews) > 5:
                    print(f"... 还有 {len(previews)-5} 个修改")

                confirm = input("\n确认修改? (y/N): ").strip().lower()
                if confirm == 'y':
                    modified_descriptions = generator.apply_batch_modifications(
                        descriptions, modifications, selected_indices
                    )

                    # 保存修改后的描述
                    new_video_name = f"{video_name}_batch_modified"
                    generator.save_descriptions(modified_descriptions, new_video_name)
                else:
                    print("❌ 修改已取消")
            else:
                print("❌ 没有有效的修改规则")
        else:
            print("❌ 未找到指定视频的描述")

    elif choice == "4":
        # 单独修改（新功能）
        video_name = input("请输入要修改的视频名称: ").strip()
        descriptions = generator.load_descriptions(video_name)

        if descriptions:
            print(f"\n📋 加载到 {len(descriptions)} 条描述")
            print("\n=== 单独修改模式 ===")

            # 显示所有描述
            for i, desc in enumerate(descriptions):
                print(f"{i+1}. {desc.current_description}")

            # 选择要修改的描述
            try:
                index = int(input("\n请输入要修改的描述编号: ").strip()) - 1
                if 0 <= index < len(descriptions):
                    desc = descriptions[index]
                    print(f"\n当前描述: {desc.current_description}")
                    print("\n请输入修改规则 (多个规则用逗号分隔):")
                    print("格式: 旧词->新词 (如: 室内->户外, 猫->狗)")

                    rules_input = input("修改规则: ").strip()
                    if rules_input:
                        # 解析规则
                        modifications = {}
                        for rule in rules_input.split(','):
                            if '->' in rule:
                                old, new = rule.split('->', 1)
                                modifications[old.strip()] = new.strip()

                        if modifications:
                            # 应用修改
                            modified_desc = generator.apply_single_modification(
                                desc, modifications
                            )

                            print(f"\n修改后: {modified_desc.current_description}")

                            # 更新描述列表
                            descriptions[index] = modified_desc

                            # 保存
                            confirm = input("\n保存修改? (y/N): ").strip().lower()
                            if confirm == 'y':
                                new_video_name = f"{video_name}_single_modified"
                                generator.save_descriptions(descriptions, new_video_name)
                        else:
                            print("❌ 没有有效的修改规则")
                    else:
                        print("❌ 请输入修改规则")
                else:
                    print("❌ 无效的编号")
            except ValueError:
                print("❌ 请输入有效的数字")
        else:
            print("❌ 未找到指定视频的描述")

    elif choice == "5":
        # 撤销修改（新功能）
        video_name = input("请输入要撤销修改的视频名称: ").strip()
        descriptions = generator.load_descriptions(video_name)

        if descriptions:
            # 检查是否有修改历史
            has_history = any(desc.modification_history for desc in descriptions)
            if has_history:
                print(f"\n📋 加载到 {len(descriptions)} 条描述")
                steps = int(input("要撤销多少步操作? (默认1): ").strip() or "1")

                restored_descriptions = generator.undo_modifications(descriptions, steps)

                # 保存恢复的描述
                new_video_name = f"{video_name}_restored"
                generator.save_descriptions(restored_descriptions, new_video_name)
            else:
                print("❌ 没有可撤销的修改历史")
        else:
            print("❌ 未找到指定视频的描述")

    elif choice == "6":
        # 翻译描述
        video_name = input("请输入要翻译的视频名称: ").strip()
        descriptions = generator.load_descriptions(video_name)

        if descriptions:
            target_lang = input("请输入目标语言 (en/zh，默认en): ").strip() or "en"

            print(f"\n🌐 开始翻译 {len(descriptions)} 条描述...")
            translated_descriptions = asyncio.run(
                generator.translate_descriptions(descriptions, target_lang)
            )

            # 保存翻译结果
            new_video_name = f"{video_name}_{target_lang}"
            generator.save_descriptions(translated_descriptions, new_video_name)
        else:
            print("❌ 未找到指定视频的描述")

    elif choice == "7":
        # 查看已保存描述
        desc_files = list(generator.descriptions_path.glob("*_descriptions.json"))

        if desc_files:
            print(f"\n📚 已保存的描述文件:")
            for i, file in enumerate(desc_files, 1):
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    video_name = data.get('video_name', file.stem.replace('_descriptions', ''))
                    count = data.get('total_descriptions', 0)
                    created = data.get('created_at', 0)

                    print(f"{i}. {video_name} - {count} 条描述 (创建时间: {time.ctime(created)})")
                except Exception as e:
                    print(f"{i}. {file.name} - 文件损坏: {e}")
        else:
            print("\n📭 暂无已保存的描述文件")

    else:
        print("❌ 无效选择")

    print("\n" + "=" * 60)
    print("🎉 描述生成模块运行完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
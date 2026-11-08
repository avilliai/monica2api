"""
Monica API 数据模型
"""
from typing import Optional, List, Any
from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """文件信息"""
    file_url: str
    file_uid: str
    parse: bool = True
    file_name: str
    file_size: int
    file_type: str
    file_ext: str
    file_tokens: int = 0
    file_chunks: int = 0
    object_url: Optional[str] = None
    file_meta_info: Optional[dict] = None
    use_full_text: bool = True


class ItemContent(BaseModel):
    """消息内容"""
    type: str = "text"
    content: str = ""
    max_token: Optional[int] = None
    is_incognito: bool = True
    from_task_type: Optional[str] = None
    manual_web_search_enabled: bool = False
    use_model: Optional[str] = None
    file_infos: Optional[List[FileInfo]] = None


class Item(BaseModel):
    """对话项"""
    conversation_id: str
    parent_item_id: Optional[str] = None
    item_id: str
    item_type: str  # "question" | "reply"
    data: ItemContent


class DataField(BaseModel):
    """数据字段"""
    conversation_id: str
    pre_parent_item_id: str
    items: List[Item]
    trigger_by: str = "auto"
    use_model: Optional[str] = None
    is_incognito: bool = True
    use_new_memory: bool = False


class ToolData(BaseModel):
    """工具数据"""
    sys_skill_list: List[str] = Field(default_factory=list)


class MonicaRequest(BaseModel):
    """Monica API 请求"""
    task_uid: str
    bot_uid: str
    data: DataField
    language: str = "auto"
    task_type: str = "chat"
    tool_data: ToolData = Field(default_factory=ToolData)


class CustomBotData(BaseModel):
    """Custom Bot 数据字段"""
    conversation_id: str
    items: List[Item]
    pre_generated_reply_id: str
    pre_parent_item_id: str
    origin: str
    origin_page_title: str
    trigger_by: str = "auto"
    use_model: str
    is_incognito: bool = False
    use_new_memory: bool = True
    use_memory_suggestion: bool = True


class BotToolData(BaseModel):
    """Bot 工具数据"""
    knowledge_list: List[Any] = Field(default_factory=list)
    user_skill_list: List[Any] = Field(default_factory=list)
    sys_skill_list: List[Any] = Field(default_factory=list)
    use_model: str
    schedule_task_list: List[Any] = Field(default_factory=list)


class BotData(BaseModel):
    """Bot 配置数据"""
    description: str
    logo_url: str
    name: str
    classification: str = "custom"
    prompt: str
    type: str = "custom_bot"
    uid: str
    example_list: List[Any] = Field(default_factory=list)
    tool_data: BotToolData


class CustomBotRequest(BaseModel):
    """Custom Bot 请求"""
    task_uid: str
    bot_uid: str
    data: CustomBotData
    language: str = "auto"
    locale: str = "zh_CN"
    task_type: str = "chat"
    bot_data: BotData
    ai_resp_language: Optional[str] = "Chinese (Simplified)"


class MonicaSSEData(BaseModel):
    """Monica SSE 数据"""
    text: str = ""
    finished: bool = False
    agent_status: Optional[dict] = None

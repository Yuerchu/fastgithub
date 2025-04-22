import configparser
import os, re
from pydantic import BaseModel, field_validator, Field

class AppConfig(BaseModel):
    host: str = Field(default="0.0.0.0", description='主机名')
    port: int = Field(default=8000, ge=1, le=65535, description='端口号')
    debug: bool = Field(default=False, description='是否启用调试')
    chunk_size: int = Field(default=1024 * 10, description='分片大小')
    size_limit: int = Field(default=1024 * 1024 * 1024 * 999, description='大小限制')
    jsdelivr: int = Field(default=0, description='分支文件使用jsDelivr镜像的开关，0为关闭，默认关闭')

    @field_validator('host')
    def validate_host(cls, v):
        # 简单的IP地址验证或允许localhost
        if v == 'localhost':
            return v
        
        parts = v.split('.')
        if len(parts) != 4:
            raise ValueError("IP地址格式错误")
            
        ip_regx = re.compile(
                pattern=r'^'
                r'(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9][0-9]|[0-9])'  # 第一段
                r'\.'
                r'(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9][0-9]|[0-9])'  # 第二段
                r'\.'
                r'(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9][0-9]|[0-9])'  # 第三段
                r'\.'
                r'(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9][0-9]|[0-9])'  # 第四段
                r'$'
            )
        if not bool(ip_regx.match(v)):
            raise ValueError('主机名填写错误，请检查')
        
        return v

class Config:
    def __init__(self, config_path='config.ini'):
        self.config_path = config_path
        self.config_parser = configparser.ConfigParser()
        self.app_config = None
        
        # 读取或创建配置
        self._load_or_create_config()
    
    def _load_or_create_config(self):
        """加载现有配置或创建新配置"""
        # 尝试读取配置文件
        if os.path.exists(self.config_path):
            self.config_parser.read(self.config_path)
        
        # 确保app节存在
        if not self.config_parser.has_section('app'):
            self.config_parser.add_section('app')
            
        # 从配置解析器中提取当前app配置
        app_dict = {}
        if self.config_parser.has_section('app'):
            app_dict = dict(self.config_parser.items('app'))
        
        # 转换为适当的类型
        if 'debug' in app_dict:
            app_dict['debug'] = app_dict['debug'].lower() in ('true', '1', 'yes')
        if 'port' in app_dict:
            app_dict['port'] = int(app_dict['port'])
        if 'chunk_size' in app_dict:
            app_dict['chunk_size'] = int(app_dict['chunk_size'])
        if 'size_limit' in app_dict:
            app_dict['size_limit'] = int(app_dict['size_limit'])
            
        # 使用pydantic验证并创建配置对象
        self.app_config = AppConfig(**app_dict)
        
        # 将验证后的配置保存回配置解析器
        self._update_config_parser()
        
        # 保存到文件
        self.save()
    
    def _update_config_parser(self):
        """将 app_config 的内容更新到 config_parser"""
        app_dict = self.app_config.model_dump()  # 使用 model_dump() 替代 dict()
        for key, value in app_dict.items():
            self.config_parser.set('app', key, str(value))
    
    def save(self):
        """保存配置到文件"""
        with open(self.config_path, 'w') as f:
            self.config_parser.write(f)
    
    def get(self, param: str):
        """获取配置参数值"""
        if hasattr(self.app_config, param):
            return getattr(self.app_config, param)
        raise ValueError(f"配置参数 '{param}' 不存在")
    
    def set(self, param: str, value):
        """设置配置参数值"""
        if hasattr(self.app_config, param):
            # 使用Pydantic的验证机制设置值
            updated_data = self.app_config.model_dump()  # 使用 model_dump() 替代 dict()
            updated_data[param] = value
            self.app_config = AppConfig(**updated_data)
            # 更新配置解析器并保存
            self._update_config_parser()
            self.save()
        else:
            raise ValueError(f"配置参数 '{param}' 不存在")
    
    def reset(self):
        """重置为默认配置"""
        self.app_config = AppConfig()
        self._update_config_parser()
        self.save()
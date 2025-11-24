# Word模板新增字段使用说明

## 新增的模板变量

在Word模板中，现在可以使用以下新增的变量：

### 1. 项目目标 (project_goal)
- **变量名**: `{{ project_goal }}`
- **类型**: 文本
- **说明**: 显示项目的目标描述
- **使用示例**: 
  ```
  项目目标：{{ project_goal }}
  ```

### 2. 项目状态 (project_status)
- **变量名**: `{{ project_status }}`
- **类型**: 文本
- **说明**: 显示项目状态（进行中、已完成、暂停、待启动、已取消）
- **默认值**: 如果未设置，默认为"进行中"
- **使用示例**: 
  ```
  项目状态：{{ project_status }}
  ```

### 3. 医院Logo (hospital_logo)
- **变量名**: `{{ hospital_logo }}`
- **类型**: 图片对象（InlineImage）
- **说明**: 显示医院的Logo图片
- **使用示例**: 
  ```
  {% if hospital_logo %}
  {{ hospital_logo }}
  {% endif %}
  ```
  
  或者直接使用：
  ```
  {{ hospital_logo }}
  ```
  
  如果logo不存在，变量为None，不会显示任何内容。

## 在Word模板中的使用方法

### 方法1：使用Jinja2语法（推荐）

1. **插入文本变量**：
   - 在Word中，直接输入 `{{ project_goal }}` 或 `{{ project_status }}`
   - docxtpl会自动替换为实际值

2. **插入图片**：
   - 在Word中，输入 `{{ hospital_logo }}`
   - 如果logo存在，会自动插入图片
   - 图片宽度设置为40mm（约150像素）

3. **条件显示**：
   ```
   {% if project_goal %}
   项目目标：{{ project_goal }}
   {% endif %}
   
   {% if hospital_logo %}
   {{ hospital_logo }}
   {% endif %}
   ```

### 方法2：使用Word书签（如果支持）

如果模板使用书签方式，可以在Word中插入书签：
- `project_goal`
- `project_status`
- `hospital_logo`

## 完整示例

在Word模板的适当位置，可以这样使用：

```
项目名称：{{ project_name }}
医院名称：{{ hospital_name }}
项目状态：{{ project_status }}

{% if hospital_logo %}
{{ hospital_logo }}
{% endif %}

项目目标：
{{ project_goal }}

项目经理：{{ project_manager }}
研发经理：{{ dev_manager }}
商务经理：{{ business_manager }}
```

## 注意事项

1. **Logo路径**：Logo文件存储在 `static/uploads/logos/` 目录下
2. **Logo格式**：支持 JPG、PNG、GIF、WEBP 格式
3. **Logo大小**：在Word中显示宽度为40mm，高度按比例自动调整
4. **空值处理**：如果字段为空，会显示空字符串或默认值
5. **图片加载失败**：如果logo文件不存在或加载失败，不会显示图片，也不会报错

## 更新模板步骤

1. 打开Word模板文件：`templates/word_templates/weekly_report_template.docx`
2. 在需要显示新字段的位置，输入相应的变量名（如 `{{ project_goal }}`）
3. 保存模板文件
4. 重新生成周报，新字段会自动填充



from datetime import date, datetime

from pydantic import BaseModel, Field

# 框数上限。单条记录 2D/3D 各十万框已经远超任何真实场景（一张图几百框量级），
# 留足余量只为挡住「手抖多按几个 0」把聚合数字污染成天文数字。
MAX_BOXES = 1_000_000


class AnnotationCreate(BaseModel):
    project_id: int
    work_date: date
    # 条目号是**字符串**不是整数：真实条目号会写成 `007`、`A-001` 这类形态。
    # 存整数会让 `007` 和 `7` 塌缩成同一行——而条目号正是质检通过率的聚合键，
    # 塌缩之后算出来是错的，且不报任何错。
    item_no: str = Field(default="", max_length=64)
    box2d: int = Field(default=0, ge=0, le=MAX_BOXES)
    box3d: int = Field(default=0, ge=0, le=MAX_BOXES)
    remark: str = Field(default="", max_length=255)
    # 代填。空或等于自己 → 归自己；在自己范围内 → 代填 + 留痕；
    # **越权 → 404**（不是静默归到自己名下，那样会凭空产生一条错数据且不报错）。
    user_id: int | None = None


class AnnotationUpdate(BaseModel):
    """改记录。**不含 project_id / work_date**：

    这两项是「疑似重复」探测键的一部分，改它等于把记录搬到另一个键上，
    与「新建一条」没有区别，而新建是允许的（重复不拦）。
    放开改反而会绕开填报日期闸门——把日期改成 100 天前，就等于改了历史。
    """
    item_no: str | None = Field(default=None, max_length=64)
    box2d: int | None = Field(default=None, ge=0, le=MAX_BOXES)
    box3d: int | None = Field(default=None, ge=0, le=MAX_BOXES)
    remark: str | None = Field(default=None, max_length=255)


class AnnotationOut(BaseModel):
    id: int
    user_id: int
    # 冗余展示字段，省前端一次查询
    user_name: str = ""
    project_id: int
    project_name: str = ""
    work_date: date
    item_no: str = ""
    box2d: int = 0
    box3d: int = 0
    # ★ 工作量口径 = 2D + 3D。这条不是拍的：设计稿「总工作量 1,239,698」
    #   正好等于那 5 行 mock 数据的 3D 合计 1,238,036 + 2D 合计 1,662。
    box_total: int = 0
    remark: str = ""
    edited_by_manager: bool = False
    # 同人 + 同项目 + 同天 + 同条目号 已经有了别的记录。
    # ★ **只是提示，不是错误**：规则明确「允许重复，只提示不拦」，
    #   所以创建时返回的是 201 + 这个 true，而不是 409。
    #   它是**算出来的**、不落库——存下来就会把「当时看起来像重复」这个判断
    #   冻结成事实，而随着数据增删它会变。
    suspected_duplicate: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AnnotationPage(BaseModel):
    """列表信封。

    ★ 不返回裸数组是有原因的：前端要分页，而且**导出行数必须能和同参数的
      total 对账**（回归里有一条断言专门钉它）。裸数组给不出总数，
      「导出的和列表看到的不是同一批」这类问题就永远发现不了——
      而它恰恰是最容易悄悄发生的一类 bug（两个接口各写一遍筛选）。
    """
    items: list[AnnotationOut]
    total: int

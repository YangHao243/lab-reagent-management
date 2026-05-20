"""修复清洗剂3/4和三氯甲烷因 seed 名称不匹配产生的 3 条重复记录。

运行方式：
    python fix_reagent_duplicate_names.py

该脚本会：
1. 自动备份当前数据库
2. 将重复新记录的 name_en 合并到保留的旧记录
3. 删除无业务数据的新重复记录
4. 修复后预置试剂总数恢复为 19 条
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select

from database import SessionLocal, engine, init_db
from models import InventoryRecord, Reagent


BACKEND_DIR = Path(__file__).resolve().parent
DB_PATH = BACKEND_DIR / "lab_reagent.db"


def backup_database() -> Path:
    """备份当前数据库文件。"""

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = BACKEND_DIR / f"lab_reagent.db.backup-before-fix-{timestamp}"
    shutil.copy2(DB_PATH, backup_path)
    print(f"数据库已备份到：{backup_path.name}")
    return backup_path


DUPLICATE_GROUPS: list[dict] = [
    {
        "label": "清洗剂3",
        "target_name_cn": "清洗剂3 (三氯乙烯)",
        "name_en": "Trichloroethylene (TCE)",
        "old_name_cn_keyword": "清洗剂3 ",
        "new_name_cn_keyword": "清洗剂3#",
    },
    {
        "label": "清洗剂4",
        "target_name_cn": "清洗剂4 (n甲基吡咯烷酮)",
        "name_en": "N-Methyl-2-pyrrolidone (NMP)",
        "old_name_cn_keyword": "清洗剂4 ",
        "new_name_cn_keyword": "清洗剂4#",
    },
    {
        "label": "三氯甲烷",
        "target_name_cn": "三氯甲烷",
        "name_en": "Chloroform",
        "old_name_cn_keyword": "三氯甲烷",
        "new_name_cn_keyword": "三氯甲烷（AR）",
    },
]


def fix() -> None:
    init_db()
    db = SessionLocal()

    try:
        for group in DUPLICATE_GROUPS:
            print(f"\n=== 处理 {group['label']} ===")

            # 查找旧记录（保留对象）和新记录（待删除对象）
            old_reagent = db.execute(
                select(Reagent).where(
                    Reagent.name_cn.contains(group["old_name_cn_keyword"]),
                    ~Reagent.name_cn.contains("#"),
                    ~Reagent.name_cn.contains("（AR）"),
                )
            ).scalar_one_or_none()

            new_reagent = db.execute(
                select(Reagent).where(
                    Reagent.name_cn.contains(group["new_name_cn_keyword"]),
                )
            ).scalar_one_or_none()

            if old_reagent is None and new_reagent is None:
                print("  未发现相关记录，跳过")
                continue

            if old_reagent is not None and new_reagent is not None:
                # 两条记录都存在：合并 name_en 到旧记录，删除新记录
                print(f"  旧记录 ID={old_reagent.id}  name_cn={old_reagent.name_cn}")
                print(f"  新记录 ID={new_reagent.id}  name_cn={new_reagent.name_cn}")

                # 检查新记录是否有库存流水
                new_inv_count = db.execute(
                    select(func.count(InventoryRecord.id)).where(
                        InventoryRecord.reagent_id == new_reagent.id
                    )
                ).scalar_one()

                if new_inv_count > 0:
                    print(f"  WARNING: 新记录 ID={new_reagent.id} 有 {new_inv_count} 条库存流水，不能直接删除！")
                    print("  请手动处理后再运行此脚本。")
                    continue

                # 转移 name_en 到旧记录
                if new_reagent.name_en and not old_reagent.name_en:
                    old_reagent.name_en = new_reagent.name_en
                    print(f"  已将 name_en '{new_reagent.name_en}' 写入旧记录 ID={old_reagent.id}")

                # 确保旧记录 name_cn 使用目标格式
                old_reagent.name_cn = group["target_name_cn"]
                print(f"  已将旧记录 name_cn 更新为 '{group['target_name_cn']}'")

                # 删除新重复记录
                db.delete(new_reagent)
                print(f"  已删除重复记录 ID={new_reagent.id}")

            elif old_reagent is not None and new_reagent is None:
                # 只有旧记录：更新 name_cn 和 name_en
                print(f"  仅存在旧记录 ID={old_reagent.id}  name_cn={old_reagent.name_cn}")
                old_reagent.name_cn = group["target_name_cn"]
                if not old_reagent.name_en:
                    old_reagent.name_en = group["name_en"]
                print(f"  已更新 name_cn='{group['target_name_cn']}'  name_en='{group['name_en']}'")

            elif old_reagent is None and new_reagent is not None:
                # 只有新记录：改名
                print(f"  仅存在新记录 ID={new_reagent.id}  name_cn={new_reagent.name_cn}")
                new_reagent.name_cn = group["target_name_cn"]
                if not new_reagent.name_en:
                    new_reagent.name_en = group["name_en"]
                print(f"  已更新 name_cn='{group['target_name_cn']}'")

        db.commit()
        print("\n数据库修复已提交")

        # 打印最终结果
        total = db.execute(select(func.count(Reagent.id))).scalar_one()
        print(f"\n当前试剂总数：{total}")
        print("\n所有试剂：")
        for r in db.execute(
            select(Reagent).order_by(Reagent.id.asc())
        ).scalars().all():
            print(f"  ID={r.id}  name_cn={r.name_cn}  name_en={r.name_en}  purity_grade={r.purity_grade}")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    backup_database()
    fix()

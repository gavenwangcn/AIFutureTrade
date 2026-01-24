-- 为 trades 表添加 position_side 字段，并迁移数据
-- 执行此脚本前，请确保已备份数据库

-- 检查并添加 position_side 字段
SET @db_name = DATABASE();
SET @table_name = 'trades';
SET @column_exists = (
    SELECT COUNT(*) 
    FROM information_schema.COLUMNS 
    WHERE TABLE_SCHEMA = @db_name 
    AND TABLE_NAME = @table_name 
    AND COLUMN_NAME = 'position_side'
);

-- 如果 position_side 字段不存在，添加字段并迁移数据
SET @sql = IF(@column_exists = 0,
    CONCAT('ALTER TABLE `', @table_name, '` ',
           'ADD COLUMN `position_side` VARCHAR(10) DEFAULT ''LONG'' COMMENT ''持仓方向：LONG（做多）或SHORT（做空）'' AFTER `side`, ',
           'ADD INDEX `idx_position_side` (`position_side`)'),
    'SELECT ''Column position_side already exists, skipping...'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 如果字段已存在但数据未迁移，执行数据迁移
SET @migration_needed = (
    SELECT COUNT(*) 
    FROM information_schema.COLUMNS 
    WHERE TABLE_SCHEMA = @db_name 
    AND TABLE_NAME = @table_name 
    AND COLUMN_NAME = 'position_side'
);

-- 迁移数据：将side字段的值（LONG/SHORT）复制到position_side
SET @migrate_sql = IF(@migration_needed > 0,
    CONCAT('UPDATE `', @table_name, '` ',
           'SET `position_side` = UPPER(`side`) ',
           'WHERE (`position_side` IS NULL OR `position_side` = '''') ',
           'AND `side` IN (''LONG'', ''SHORT'', ''long'', ''short'')'),
    'SELECT ''Migration not needed'' AS message'
);

PREPARE migrate_stmt FROM @migrate_sql;
EXECUTE migrate_stmt;
DEALLOCATE PREPARE migrate_stmt;

-- 更新side字段：根据signal转换为buy/sell
-- buy_to_long, buy_to_short -> buy
-- sell_to_long, sell_to_short, close_position, stop_loss, take_profit -> sell
SET @update_side_sql = CONCAT('UPDATE `', @table_name, '` ',
    'SET `side` = CASE ',
    '    WHEN `signal` LIKE ''buy%'' THEN ''buy'' ',
    '    WHEN `signal` LIKE ''sell%'' OR `signal` = ''close_position'' OR `signal` = ''stop_loss'' OR `signal` = ''take_profit'' THEN ''sell'' ',
    '    ELSE `side` ',
    'END ',
    'WHERE `side` IN (''LONG'', ''SHORT'', ''long'', ''short'')');

PREPARE update_stmt FROM @update_side_sql;
EXECUTE update_stmt;
DEALLOCATE PREPARE update_stmt;

SELECT 'Migration completed successfully!' AS message;

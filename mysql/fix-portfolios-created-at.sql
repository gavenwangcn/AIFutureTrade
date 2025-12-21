-- 修复 portfolios 表，添加缺失的 created_at 字段
-- 执行此脚本以修复现有数据库

-- 检查字段是否存在，如果不存在则添加
SET @db_name = DATABASE();
SET @table_name = 'portfolios';
SET @column_name = 'created_at';

SET @column_exists = (
    SELECT COUNT(*) 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = @db_name 
    AND TABLE_NAME = @table_name 
    AND COLUMN_NAME = @column_name
);

SET @sql = IF(@column_exists = 0,
    CONCAT('ALTER TABLE `', @table_name, '` ADD COLUMN `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP AFTER `unrealized_profit`'),
    'SELECT "Column created_at already exists" AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 如果字段已存在但为 NULL，更新现有记录
UPDATE `portfolios` 
SET `created_at` = `updated_at` 
WHERE `created_at` IS NULL;


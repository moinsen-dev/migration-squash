-- Add more columns to existing tables
ALTER TABLE users ADD COLUMN last_login TIMESTAMP;
ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1;

ALTER TABLE projects ADD COLUMN is_public BOOLEAN DEFAULT 0;
ALTER TABLE projects ADD COLUMN updated_at TIMESTAMP;

-- Add a trigger to update the updated_at timestamp
CREATE TRIGGER update_projects_timestamp
AFTER UPDATE ON projects
BEGIN
    UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
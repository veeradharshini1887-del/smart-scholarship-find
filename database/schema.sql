-- =====================================================================
-- Smart Scholarship Finder & Career Guidance System  -  MySQL schema
-- Run once:   mysql -u root -p < database/schema.sql
-- Safe to re-run: tables use IF NOT EXISTS and demo rows use INSERT IGNORE.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS smart_scholarship
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE smart_scholarship;

-- ---------------------------------------------------------------------
-- Student  (email + password_hash added for login; profile fields are
-- NULL until the student completes the Student Profile form)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS student (
  student_id     INT AUTO_INCREMENT PRIMARY KEY,
  name           VARCHAR(100) NOT NULL,
  email          VARCHAR(150) NOT NULL UNIQUE,
  password_hash  VARCHAR(255) NOT NULL,
  college        VARCHAR(150) NULL,
  degree         VARCHAR(50)  NULL,
  cgpa           DECIMAL(4,2) NULL,
  family_income  DECIMAL(12,2) NULL,
  community      VARCHAR(30)  NULL,
  gender         VARCHAR(10)  NULL,
  state          VARCHAR(60)  NULL,
  created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Scholarship
--   degree / community / state : 'ALL' or a comma separated list
--   gender                     : 'All', 'Male', 'Female' or 'Other'
--   maximum_income             : 0 means "no income limit"
--   minimum_cgpa               : 0 means "no CGPA limit"
--   is_demo                    : 1 = sample data, 0 = verified by admin
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scholarship (
  scholarship_id     INT AUTO_INCREMENT PRIMARY KEY,
  scholarship_name   VARCHAR(150) NOT NULL UNIQUE,
  amount             DECIMAL(12,2) NOT NULL DEFAULT 0,
  eligibility        TEXT NOT NULL,
  minimum_cgpa       DECIMAL(4,2) NOT NULL DEFAULT 0,
  maximum_income     DECIMAL(12,2) NOT NULL DEFAULT 0,
  degree             VARCHAR(255) NOT NULL DEFAULT 'ALL',
  community          VARCHAR(255) NOT NULL DEFAULT 'ALL',
  gender             VARCHAR(10)  NOT NULL DEFAULT 'All',
  state              VARCHAR(255) NOT NULL DEFAULT 'ALL',
  required_documents VARCHAR(255) NOT NULL,
  last_date          DATE NOT NULL,
  official_link      VARCHAR(255) NULL,
  is_demo            TINYINT(1) NOT NULL DEFAULT 1,
  created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Application
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS application (
  application_id     INT AUTO_INCREMENT PRIMARY KEY,
  student_id         INT NOT NULL,
  scholarship_id     INT NOT NULL,
  application_status ENUM('Submitted','Under Review','Approved','Rejected')
                     NOT NULL DEFAULT 'Submitted',
  applied_date       DATE NOT NULL,
  UNIQUE KEY uq_student_scholarship (student_id, scholarship_id),
  CONSTRAINT fk_app_student
    FOREIGN KEY (student_id) REFERENCES student(student_id) ON DELETE CASCADE,
  CONSTRAINT fk_app_scholarship
    FOREIGN KEY (scholarship_id) REFERENCES scholarship(scholarship_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Document  (each column stores the relative path of the uploaded file)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document (
  document_id           INT AUTO_INCREMENT PRIMARY KEY,
  student_id            INT NOT NULL UNIQUE,
  aadhaar               VARCHAR(255) NULL,
  income_certificate    VARCHAR(255) NULL,
  marksheet             VARCHAR(255) NULL,
  community_certificate VARCHAR(255) NULL,
  updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_doc_student
    FOREIGN KEY (student_id) REFERENCES student(student_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Admin  (the first admin account is created by the app from .env)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS admin (
  admin_id       INT AUTO_INCREMENT PRIMARY KEY,
  username       VARCHAR(50) NOT NULL UNIQUE,
  password_hash  VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- DEMO DATA  -  fictional scholarships for testing only (is_demo = 1).
-- Deadlines are relative to today so reminders always work when you test.
-- Replace with verified data from the Admin Dashboard, or use the
-- "Remove all demo data" button there.
-- ---------------------------------------------------------------------
INSERT IGNORE INTO scholarship
 (scholarship_name, amount, eligibility, minimum_cgpa, maximum_income, degree, community, gender, state, required_documents, last_date, is_demo)
VALUES
('Demo Merit Scholarship for Undergraduates', 25000,
 'UG students with CGPA 8.0 or above and family income up to Rs 8,00,000 per year.',
 8.0, 800000, 'B.E.,B.Tech,B.Sc.,B.Com.,B.A.,BBA,BCA', 'ALL', 'All', 'ALL',
 'Aadhaar,Marksheet', DATE_ADD(CURDATE(), INTERVAL 25 DAY), 1),

('Demo Post Matric Scholarship (SC/ST)', 30000,
 'SC/ST students with CGPA 6.0 or above and family income up to Rs 2,50,000 per year.',
 6.0, 250000, 'ALL', 'SC,ST', 'All', 'ALL',
 'Aadhaar,Income Certificate,Marksheet,Community Certificate', DATE_ADD(CURDATE(), INTERVAL 12 DAY), 1),

('Demo BC/MBC Higher Education Scholarship', 20000,
 'BC/MBC/DNC students from Tamil Nadu with CGPA 6.5 or above and family income up to Rs 3,00,000.',
 6.5, 300000, 'ALL', 'BC,MBC,DNC', 'All', 'Tamil Nadu',
 'Aadhaar,Income Certificate,Marksheet,Community Certificate', DATE_ADD(CURDATE(), INTERVAL 40 DAY), 1),

('Demo Girls in STEM Scholarship', 40000,
 'Female students of B.E., B.Tech or B.Sc. with CGPA 7.0 or above and family income up to Rs 6,00,000.',
 7.0, 600000, 'B.E.,B.Tech,B.Sc.', 'ALL', 'Female', 'ALL',
 'Aadhaar,Income Certificate,Marksheet', DATE_ADD(CURDATE(), INTERVAL 55 DAY), 1),

('Demo Minority Community Scholarship', 15000,
 'Minority community students with CGPA 5.5 or above and family income up to Rs 2,00,000.',
 5.5, 200000, 'ALL', 'Minority', 'All', 'ALL',
 'Aadhaar,Income Certificate,Marksheet,Community Certificate', DATE_ADD(CURDATE(), INTERVAL 20 DAY), 1),

('Demo Engineering Merit-cum-Means Scholarship', 35000,
 'B.E./B.Tech students with CGPA 7.5 or above and family income up to Rs 5,00,000.',
 7.5, 500000, 'B.E.,B.Tech', 'ALL', 'All', 'ALL',
 'Aadhaar,Income Certificate,Marksheet', DATE_ADD(CURDATE(), INTERVAL 70 DAY), 1),

('Demo Rural Talent Scholarship (Karnataka)', 18000,
 'Students domiciled in Karnataka with CGPA 6.0 or above and family income up to Rs 4,00,000.',
 6.0, 400000, 'ALL', 'ALL', 'All', 'Karnataka',
 'Aadhaar,Income Certificate,Marksheet', DATE_ADD(CURDATE(), INTERVAL 33 DAY), 1),

('Demo Science Excellence Scholarship', 50000,
 'B.Sc./M.Sc. students with CGPA 8.5 or above and family income up to Rs 10,00,000.',
 8.5, 1000000, 'B.Sc.,M.Sc.', 'ALL', 'All', 'ALL',
 'Aadhaar,Marksheet', DATE_ADD(CURDATE(), INTERVAL 45 DAY), 1),

('Demo Low Income Support Grant', 12000,
 'Any degree, CGPA 5.0 or above, family income up to Rs 1,50,000 per year.',
 5.0, 150000, 'ALL', 'ALL', 'All', 'ALL',
 'Aadhaar,Income Certificate,Marksheet', DATE_ADD(CURDATE(), INTERVAL 8 DAY), 1),

('Demo Commerce and Management Scholarship', 22000,
 'B.Com., BBA, M.Com. or MBA students with CGPA 7.0 or above and family income up to Rs 7,00,000.',
 7.0, 700000, 'B.Com.,BBA,M.Com.,MBA', 'ALL', 'All', 'ALL',
 'Aadhaar,Marksheet', DATE_ADD(CURDATE(), INTERVAL 60 DAY), 1),

('Demo Women Empowerment Scholarship (Kerala)', 27000,
 'Female students domiciled in Kerala with CGPA 6.5 or above and family income up to Rs 5,00,000.',
 6.5, 500000, 'ALL', 'ALL', 'Female', 'Kerala',
 'Aadhaar,Income Certificate,Marksheet', DATE_ADD(CURDATE(), INTERVAL 28 DAY), 1),

('Demo Postgraduate Research Scholarship', 60000,
 'PG students (M.E., M.Tech, M.Sc., MCA, MBA) with CGPA 8.0 or above and family income up to Rs 12,00,000.',
 8.0, 1200000, 'M.E.,M.Tech,M.Sc.,MCA,MBA', 'ALL', 'All', 'ALL',
 'Aadhaar,Marksheet', DATE_ADD(CURDATE(), INTERVAL 90 DAY), 1),

('Demo Tamil Nadu Merit Scholarship', 20000,
 'Students domiciled in Tamil Nadu with CGPA 7.5 or above and family income up to Rs 5,00,000.',
 7.5, 500000, 'ALL', 'ALL', 'All', 'Tamil Nadu',
 'Aadhaar,Marksheet', DATE_ADD(CURDATE(), INTERVAL 36 DAY), 1),

('Demo Previous Year Scholarship (Closed)', 10000,
 'Sample of an expired scholarship, used to test the "Closed" status.',
 6.0, 500000, 'ALL', 'ALL', 'All', 'ALL',
 'Aadhaar,Marksheet', DATE_SUB(CURDATE(), INTERVAL 5 DAY), 1);

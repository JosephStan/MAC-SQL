SELECT COUNT(DISTINCT Singer_ID) FROM singer
SELECT COUNT(*) FROM singer
SELECT Name, Country, Age FROM singer ORDER BY Age DESC
SELECT Name, Country, Age FROM singer ORDER BY Age DESC
SELECT AVG(Age) as Average_Age, MIN(Age) as Minimum_Age, MAX(Age) as Maximum_Age FROM (SELECT Singer_ID, Age FROM singer WHERE Country = 'France') as French_Singers
SELECT AVG(Age) as Average_Age, MIN(Age) as Minimum_Age, MAX(Age) as Maximum_Age FROM (SELECT Singer_ID, Age FROM singer WHERE Country = 'France') as French_Singers
SELECT Song_Name, Song_release_year FROM singer WHERE Singer_ID = (SELECT Singer_ID FROM singer WHERE Age = (SELECT MIN(Age) FROM singer))
SELECT Song_Name, Song_release_year FROM singer WHERE Name = (SELECT Name FROM singer WHERE Age = (SELECT MIN(Age) FROM singer))
SELECT DISTINCT Country FROM singer WHERE Age > 20
SELECT DISTINCT Country FROM singer WHERE Age > 20

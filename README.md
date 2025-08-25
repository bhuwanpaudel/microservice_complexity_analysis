This analysis is a part of a study entitled ***"Temporal Evolution of Architectural Complexity and Technical Debt in Microservices: An Exploratory Case Study."***
Authors: Bhuwan Paudel, Javier Gonzalez-Huerta, and Ehsan Zabardast

# Microservice Complexity Analysis
A Python script to collect weekly or monthly architectural complexity indicators from a microservice.  
- Number of declared dependencies 
- Number of exposed API endpoints 
- Number of unique inter-service communications 

Each snapshot is written to CSV with the full lists of API endpoints, inter-service communications, and declared dependencies.

---

## Features

- Walks through a Maven, Node, Python, Go, and Gradle-based project.   
- Inspects dependency files (`pom.xml`, `package.json`, `requirements.txt`, etc.).  
- Parses annotations and routing calls to discover REST endpoints.  
- Scans code for HTTP, gRPC, curl, and fetch calls to count inter-service communications.   
- Checks out historical commits at weekly or monthly intervals to build a time series dataset.  
- Outputs a CSV with per-snapshot complexity indicators and lists.    

---

## Requirements

- Python 3.7+  
- A Git-initialized repo with a `main`, `master`, or `develop` branch. 
- File formats supported. 
- The `git` CLI must be available in your PATH   

---

## Usage

python microservice_complexity_analysis.py <repo_path> <output.csv> [--frequency weekly|monthly] [--periods N]

- <repo_path>: Path to the Git-tracked service directory 
- <output.csv>: Path to write the metrics CSV
- --frequency: weekly or monthly
- --periods: How many weeks or months to process


### Example
python microservice_complexity_analysis.py ~/microservices/my-service complexity_analysis/architetcural_complexity.csv --frequency weekly --periods 104

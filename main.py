"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json.
"""
import json
import os

from internshala import companies, listings, refs

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # one page of internships (40-60 per page): category + city by name or slug
    save("internships_software_development_bangalore.json",
         listings.internships(category=refs.resolve_category("Software Development"),
                              location=refs.resolve_location("Bangalore")))

    # one page of jobs: keyword, fresher-friendly boards, salary floor, experience
    save("jobs_data_scientist.json", listings.jobs(query="data scientist"))

    # an employer: profile, hiring history, salaries paid, perks, open internships and jobs
    save("company_zomato.json", companies.details(refs.resolve_company("https://internshala.com/company/zomato-1430723831")))

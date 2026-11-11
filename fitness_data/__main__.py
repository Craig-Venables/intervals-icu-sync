"""CLI entry: python -m fitness_data.charts"""

from fitness_data.charts import generate_charts

if __name__ == "__main__":
    path = generate_charts()
    print(f"Dashboard saved -> {path}")

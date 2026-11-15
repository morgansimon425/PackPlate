
"use client";

import { useState } from "react";
import { PageShell } from "@/components/PageShell";
import { api, errorMessage } from "@/lib/api";
import { useSavedProfile } from "@/lib/profileStore";
import type {
  NutritionGoal,
  RecommendationItem,
} from "@/lib/types";
import Link from "next/link";


const goals: { value: NutritionGoal; label: string }[] = [
  { value: "high_protein", label: "High Protein" },
  { value: "lower_calories", label: "Lower Calories" },
  { value: "lower_sodium", label: "Lower Sodium" },
];

function mealKey(item: RecommendationItem): string {
    return `${item.location_id}:${item.meal_periods.join(", ")}:${item.item_id}`;
}

export default function ComparePage() {
  const [goal, setGoal] = useState<NutritionGoal>("high_protein");
  const [date, setDate] = useState(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date()),
  );
  const [meal, setMeal] = useState("");
  const [results, setResults] = useState<RecommendationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searched, setSearched] = useState(false);
  const [selectedMeals, setSelectedMeals] = useState<string[]>([]);


  const savedProfile = useSavedProfile();


  function toggleMealSelection(key: string) {
    setSelectedMeals((current) => {
      if (current.includes(key)) {
        return current.filter((id) => id !== key);
      }

      if (current.length >= 2) return current;

      return [...current, key];
    });
  }

  async function findMeals() {
    setLoading(true);
    setError("");
    setSearched(false);
    setSelectedMeals([]);
    setResults([]);

    try {
        const response = await api.recommendations({
            goal,
            meal: meal || null,
            date,
            profile: savedProfile,
        });

        setResults(response.recommendations);

      setSearched(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const comparedMeals = selectedMeals
    .map((key) => results.find((item) => mealKey(item) === key))
    .filter((item): item is RecommendationItem => item !== undefined);

  return (
    <PageShell
      title="Smart Meal Comparison"
      lede="Discover meals across NC State dining locations that match your nutrition goals."
      showFreshness={false}
    >
      <section className="panel">
        <h2 className="section-title">Find Your Meals</h2>

        <div className="form">
          <div className="field">
            <label htmlFor="nutrition-goal">Nutrition Goal</label>
            <select
              id="nutrition-goal"
              className="input"
              value={goal}
              onChange={(e) =>
                setGoal(e.target.value as NutritionGoal)
              }
            >
              {goals.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="comparison-date">Menu Date</label>
            <input
                id="comparison-date"
                type="date"
                className="input"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
            />
          </div>

          <div className="field">
            <label htmlFor="meal-period">Meal Period</label>
            <select
              id="meal-period"
              className="input"
              value={meal}
              onChange={(e) => setMeal(e.target.value)}
            >
              <option value="">All Meals</option>
              <option value="breakfast">Breakfast</option>
              <option value="brunch">Brunch</option>
              <option value="lunch">Lunch</option>
              <option value="dinner">Dinner</option>
              <option value="late night">Late Night</option>
              <option value="daily">Daily</option>
            </select>
          </div>

          <div className="form">
            <div className="comparison-profile-note">
                <p>
                Your saved dietary preferences are automatically applied
                to recommendations.
                </p>
                <Link href="/profile">Update My Diet</Link>
            </div>

            <div className="button-row">
                <button
                type="button"
                className="btn"
                onClick={findMeals}
                disabled={loading}
                >
                {loading ? "Finding Meals..." : "Find Recommendations"}
                </button>
            </div>
          </div>
        </div>
      </section>

      {error && (
        <div className="state-message error" role="alert">
          {error}
        </div>
      )}

      {searched && (
        <section>
          <h2 className="section-title">
            Recommended Meals
            <span className="count">
              {results.length} found
            </span>
          </h2>

          {results.length === 0 ? (
            <div className="state-message">
              No eligible meals found. Try another nutrition
              goal or meal period.
            </div>
          ) : (
            <div className="stack">
              {results.map((item) => (
                <article
                  key={`${item.location_id}-${item.meal_periods.join(", ")}-${item.item_id}`}
                  className="panel"
                >
                  <div className="location-row">
                    <div className="location-row-head">
                      <h3 className="location-name">
                        #{item.rank} {item.name}
                      </h3>
                      <span className="pill pill-diet">
                        {item.meal_periods.join(", ")}
                      </span>
                    </div>

                    <p className="meta">
                      {item.location_name}
                    </p>

                    <button
                        type="button"
                        className="btn btn-small btn-outline"
                        aria-pressed={selectedMeals.includes(mealKey(item))}
                        disabled={
                            selectedMeals.length >= 2 &&
                            !selectedMeals.includes(mealKey(item))
                        }
                        onClick={() => toggleMealSelection(mealKey(item))}
                        >
                        {selectedMeals.includes(mealKey(item))
                            ? "Remove from Comparison"
                            : "Select to Compare"}
                    </button>
                  </div>

                  <div className="item-detail">
                    <table className="nutrition-table">
                      <tbody>
                        <tr>
                          <th scope="row">Calories</th>
                          <td>
                            {item.nutrition.calories ?? "N/A"}
                          </td>
                        </tr>
                        <tr>
                          <th scope="row">Protein</th>
                          <td>
                            {item.nutrition.protein_g == null
                              ? "N/A"
                              : `${item.nutrition.protein_g} g`}
                          </td>
                        </tr>
                        <tr>
                          <th scope="row">Sodium</th>
                          <td>
                            {item.nutrition.sodium_mg == null
                              ? "N/A"
                              : `${item.nutrition.sodium_mg} mg`}
                          </td>
                        </tr>
                      </tbody>
                    </table>

                    <p>{item.reason}</p>

                    <p className="help">
                      Serving:{" "}
                      {item.nutrition.serving_size ?? "Not listed"}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}


        {comparedMeals.length > 0 && (
        <section className="panel">
            <h2 className="section-title">Side-by-Side Comparison</h2>

            {comparedMeals.length < 2 ? (
            <p className="help">
                Select one more meal to compare nutritional information.
            </p>
            ) : (
            <>
                <p className="page-lede">
                Compare nutrition per listed serving. Serving sizes
                may differ between meals.
                </p>

                <div style={{ overflowX: "auto", marginTop: "1rem" }}>
                <table className="nutrition-table comparison-table">
                    <thead>
                    <tr>
                        <th scope="col">Nutrient</th>
                        {comparedMeals.map((item) => (
                        <th scope="col" key={mealKey(item)}>
                            {item.name}
                            <span className="meta" style={{ display: "block" }}>
                            {item.location_name}
                            </span>
                        </th>
                        ))}
                    </tr>
                    </thead>

                    <tbody>
                    {(
                        [
                        ["Calories", "calories", ""],
                        ["Protein", "protein_g", "g"],
                        ["Carbohydrates", "carbs_g", "g"],
                        ["Fat", "fat_g", "g"],
                        ["Sodium", "sodium_mg", "mg"],
                        ] as const
                    ).map(([label, field, unit]) => (
                        <tr key={field}>
                        <th scope="row">{label}</th>
                        {comparedMeals.map((item) => (
                            <td key={mealKey(item)}>
                            {item.nutrition[field] == null
                                ? "N/A"
                                : `${item.nutrition[field]} ${unit}`.trim()}
                            </td>
                        ))}
                        </tr>
                    ))}

                    <tr>
                        <th scope="row">Serving Size</th>
                        {comparedMeals.map((item) => (
                        <td key={mealKey(item)}>
                            {item.nutrition.serving_size ?? "Not listed"}
                        </td>
                        ))}
                    </tr>
                    </tbody>
                </table>
                </div>
            </>
            )}
        </section>
        )}

    </PageShell>
  );
}

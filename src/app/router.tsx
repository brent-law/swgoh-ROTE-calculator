import { Navigate, createHashRouter } from "react-router-dom";
import { LegacyPlannerLayout } from "../features/rotePlanner/LegacyPlannerLayout";
import {
  DayByDayPlanPage,
  GuidesPage,
  GuildOverviewPage,
  OperationsPage,
  PlanetPlannerPage,
  RosterPage,
} from "../features/rotePlanner/PlannerPagesLive";

export const router = createHashRouter([
  {
    path: "/",
    element: <LegacyPlannerLayout />,
    children: [
      {
        index: true,
        element: <Navigate to="/guild-overview" replace />,
      },
      {
        path: "guild-overview",
        element: <GuildOverviewPage />,
      },
      {
        path: "planet-planner",
        element: <PlanetPlannerPage />,
      },
      {
        path: "day-by-day-plan",
        element: <DayByDayPlanPage />,
      },
      {
        path: "operations",
        element: <OperationsPage />,
      },
      {
        path: "guides",
        element: <GuidesPage />,
      },
      {
        path: "roster",
        element: <RosterPage />,
      },
    ],
  },
  {
    path: "*",
    element: <Navigate to="/guild-overview" replace />,
  },
]);

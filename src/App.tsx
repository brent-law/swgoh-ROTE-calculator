import { useEffect } from "react";
import { RouterProvider } from "react-router-dom";
import { router } from "./app/router";
import { usePlannerStore } from "./state/plannerStoreCore";

function App() {
  useEffect(() => {
    void usePlannerStore.getState().hydrateFromBackend();
  }, []);

  return <RouterProvider router={router} />;
}

export default App;

import { redirect } from "next/navigation";

// The standalone map route is retired — tournament mapping now lives on the
// unified /tournaments page (Map tab), which has the list, calendar, map,
// refresh, and signup links all in one place.
export default function MapPage() {
  redirect("/tournaments");
}

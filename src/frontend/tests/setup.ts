import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// vitest globals kapalı → testing-library'nin oto-temizliği devreye girmez;
// her testten sonra DOM elle temizlenir (çift-render birikmesi tuzağı).
afterEach(cleanup);

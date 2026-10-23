import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

type RawBrandJson = {
  version: string;
  tokens: Record<string, string>;
  font_family: string;
  fonts_dir: string;
  fonts: Record<string, string>;
  contrast_pairs: [string, string, number][];
};

export interface BrandTokens {
  tokens: Record<string, string>;
  fontFamily: string;
  fontsDir: string;
  fonts: Record<string, string>;
  contrastPairs: [string, string, number][];
}

const REQUIRED_TOKENS = [
  "turquoise",
  "darkTeal",
  "lime",
  "paleBlue",
  "white",
  "black",
  "turquoise75",
  "turquoise50",
  "turquoise25",
  "darkTeal75",
  "darkTeal50",
  "darkTeal25"
];

const HEX_PATTERN = /^#[0-9A-F]{6}$/;

export function loadTokens(): BrandTokens {
  const brandPath = path.join(__dirname, "..", "..", "brand", "brand.json");

  let raw: RawBrandJson;
  try {
    const content = fs.readFileSync(brandPath, "utf-8");
    raw = JSON.parse(content) as RawBrandJson;
  } catch (err: unknown) {
    throw new Error(`Failed to read brand file at ${brandPath}: ${(err as Error).message}`);
  }

  const missingTokens: string[] = [];
  for (const token of REQUIRED_TOKENS) {
    if (!(token in raw.tokens)) {
      missingTokens.push(token);
    }
  }

  if (missingTokens.length > 0) {
    throw new Error(`missing tokens: ${missingTokens.join(", ")}`);
  }

  const invalidHex: string[] = [];
  for (const token of REQUIRED_TOKENS) {
    const value = raw.tokens[token];
    if (!HEX_PATTERN.test(value)) {
      invalidHex.push(token);
    }
  }

  if (invalidHex.length > 0) {
    throw new Error(`invalid hex format for tokens: ${invalidHex.join(", ")}`);
  }

  return {
    tokens: raw.tokens,
    fontFamily: raw.font_family,
    fontsDir: raw.fonts_dir,
    fonts: raw.fonts,
    contrastPairs: raw.contrast_pairs
  };
}

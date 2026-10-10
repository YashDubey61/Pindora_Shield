export default async function handler(req: Request): Promise<Response> {
  if (req.method !== "POST") {
    return new Response(
      JSON.stringify({ error: "Method Not Allowed" }),
      { status: 405 }
    );
  }

  try {
    const body = await req.text();

    const API_BASE = 'https://api.stat-vision.xyz';

    const backendRes = await fetch(
      `${API_BASE}/api/metrics/metrics_data`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body,
      }
    );

    const data = await backendRes.text();

    return new Response(data, {
      status: backendRes.status,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      },
    });

  } catch (err: any) {
    return new Response(
      JSON.stringify({ error: "Metrics proxy failed" }),
      { status: 500 }
    );
  }
}

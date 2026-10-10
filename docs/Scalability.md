## Scalability Plan

Pindora Shield is architected to scale progressively as data volume, model complexity, and user demand increase.

- **Modular Scaling:**  
  Each layer (generation, evaluation, backend APIs, frontend) is decoupled, allowing individual components to scale independently without impacting the entire system.

- **Model-Level Parallelism:**  
  Predictive models are independent and can be executed in parallel, enabling batch evaluation of large molecular sets and reducing overall processing time.

- **Stateless Backend APIs:**  
  The backend follows a stateless design, making it suitable for horizontal scaling using multiple instances behind a load balancer.

- **Asynchronous Job Orchestration (Planned):**  
  Future versions will introduce a task orchestrator to schedule molecule generation and evaluation jobs asynchronously, improving throughput and resource utilization.

- **Frontend Scalability:**  
  The frontend is lightweight and static-build friendly, allowing deployment on CDN-backed platforms for low-latency global access.

- **Dataset & Model Expansion:**  
  New datasets, predictive models, or evaluation metrics can be added without restructuring the existing pipeline.

This scalability strategy enables Pindora Shield to evolve from a research prototype into a production-scale drug discovery platform.

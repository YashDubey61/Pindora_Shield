# System Design – Pindora Shield

Pindora Shield is a modular, end-to-end AI-driven drug discovery system designed to bridge the gap between academic molecular generation models and practical, researcher-ready workflows. The system integrates generative modeling, multi-model molecular evaluation, backend orchestration, and an interactive frontend into a single coherent pipeline.

---

## High-Level Architecture

The system is composed of four primary layers:

1. Generative Intelligence Layer (TenGAN / TangGen)
2. Predictive Evaluation Layer (Multi-Model ML Stack)
3. Backend Orchestration Layer (API Services)
4. Frontend Interaction & Visualization Layer

Each layer is independently extensible while remaining tightly integrated through well-defined interfaces.

---

## 1. Generative Intelligence Layer

**Location:** `Tengan/`, `data/`, `3d_models/`

This layer is responsible for **de novo molecular generation**. A GAN-based model (TenGAN / TangGen), trained on large molecular datasets such as QM9 and ZINC, generates novel and chemically valid SMILES representations.

**Responsibilities:**
- Explore chemical space beyond known drugs
- Generate structurally diverse molecular candidates
- Maintain chemical validity and synthesizability

**Outputs:**
- Generated SMILES strings (`generated_molecules.json`)
- Optional 3D molecular structures (`.sdf`)

---

## 2. Predictive Evaluation Layer

**Location:** `matriX_model/`, `utils/`

Each generated molecule is evaluated using **independent, specialized machine learning models**, each optimized for a single pharmacological property.

**Evaluated Properties:**
- IC50 (potency prediction)
- Target–drug association score
- Clinical phase likelihood
- Target relevance
- Drug-likeness and feasibility metrics

Instead of a single multi-task model, separate models are used to improve accuracy, interpretability, and ease of debugging.

---

## 3. Backend Orchestration Layer

**Location:** `routes/`, `pindora.py`, `main.py`

The backend serves as the **central coordinator** of the system. It exposes REST APIs that connect the generative models, predictive evaluators, and frontend clients.

**Core Responsibilities:**
- Accept disease or biological intent as input
- Trigger molecular generation
- Sequentially evaluate each generated molecule
- Filter and rank candidates
- Aggregate results into structured JSON responses

**Key Endpoints:**
- `/api/drug_discovery`
- `/metrics/metrics_data`
- Health and validation endpoints

The backend is designed to remain stateless and scalable, enabling future deployment across distributed environments.

---

## 4. Frontend Interaction & Visualization Layer

**Location:** `frontend/`

The frontend provides a researcher-friendly interface for interacting with the system and interpreting results.

**Features:**
- Natural language disease input
- Real-time generation status feedback
- Detailed molecular property visualization
- Interactive 3D molecule rendering (WebGL)
- Comparative analysis views

The frontend abstracts away backend and ML complexity, allowing researchers to focus on scientific insights rather than system mechanics.

---

## End-to-End Workflow

1. User provides disease or biological intent
2. Relevant targets are identified
3. TenGAN generates novel molecular SMILES
4. Each molecule is evaluated by multiple ML models
5. Low-potential candidates are filtered
6. Top-ranked molecules are returned
7. Results and 3D structures are visualized in the frontend

---

## Design Rationale

- Modular architecture enables scalability and maintainability
- Independent predictive models improve accuracy and interpretability
- End-to-end automation reduces manual intervention
- Research-ready outputs support downstream decision-making





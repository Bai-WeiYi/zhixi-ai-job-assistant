export type InterviewQuestion = {
  question: string;
  purpose: string;
  answer_points: string[];
};

export type AnalysisResult = {
  match_score: number;
  summary: string;
  strengths: string[];
  gaps: string[];
  resume_suggestions: string[];
  interview_questions: InterviewQuestion[];
};

export type AnalysisResponse = {
  id: number;
  result: AnalysisResult;
  model_name: string;
  prompt_version: string;
  duration_ms: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  created_at: string;
};

export type InterviewFeedback = {
  score: number;
  summary: string;
  strengths: string[];
  improvements: string[];
  suggested_answer_points: string[];
};

export type KnowledgeReference = {
  document_id: number;
  title: string;
  content: string;
  similarity: number;
};

export type InterviewAttempt = {
  id: number;
  analysis_id: number;
  question_number: number;
  question_text: string;
  answer_text: string;
  feedback: InterviewFeedback;
  model_name: string;
  prompt_version: string;
  duration_ms: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  references: KnowledgeReference[];
  created_at: string;
};

export type AdaptiveQuestion = {
  turn_id: number;
  round_number: number;
  source: "main" | "follow_up";
  source_question_number: number | null;
  question: string;
  purpose: string;
  answer_points: string[];
};

export type AdaptiveTurn = {
  id: number;
  round_number: number;
  source: "main" | "follow_up";
  source_question_number: number | null;
  question: string;
  purpose: string;
  answer_text: string | null;
  feedback: InterviewFeedback | null;
  model_name: string | null;
  prompt_version: string | null;
  duration_ms: number | null;
  total_tokens: number | null;
  references: KnowledgeReference[];
  route_decision: "follow_up" | "next_main" | "finish" | null;
  created_at: string;
  answered_at: string | null;
};

export type AdaptiveInterviewReport = {
  overall_score: number;
  summary: string;
  strengths: string[];
  improvements: string[];
  action_plan: string[];
};

export type WorkflowTraceEvent = {
  node: string;
  duration_ms: number;
  detail: string;
};

export type AdaptiveInterviewSession = {
  id: number;
  analysis_id: number;
  status: "processing" | "awaiting_answer" | "completed";
  workflow_version: string;
  max_rounds: number;
  completed_turns: number;
  current_node: string;
  current_question: AdaptiveQuestion | null;
  turns: AdaptiveTurn[];
  report: AdaptiveInterviewReport | null;
  execution_path: WorkflowTraceEvent[];
  total_tokens: number;
  duration_ms: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type AdaptiveInterviewSessionListItem = {
  id: number;
  status: AdaptiveInterviewSession["status"];
  completed_turns: number;
  max_rounds: number;
  overall_score: number | null;
  created_at: string;
  updated_at: string;
};

export type AnalysisListItem = {
  id: number;
  match_score: number;
  summary: string;
  job_description_preview: string;
  model_name: string;
  created_at: string;
};

export type ParsedResume = {
  text: string;
  page_count: number;
  character_count: number;
};

export type User = {
  id: number;
  email: string;
  created_at: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  user: User;
};

export type UsageQuota = {
  used: number;
  limit: number;
  remaining: number;
  reset_at: string;
};

export type UsageSummary = {
  analysis: UsageQuota;
  interview: UsageQuota;
  knowledge: UsageQuota;
};

export type KnowledgeDocument = {
  id: number;
  title: string;
  source_type: "pdf" | "text";
  filename: string | null;
  character_count: number;
  chunk_count: number;
  created_at: string;
};

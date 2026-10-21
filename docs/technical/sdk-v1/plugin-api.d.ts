/** Proposed SDK plugin API 1.0.0; not installed in the current main runtime. */
export type JsonValue = null | boolean | number | string | readonly JsonValue[] | { readonly [key: string]: JsonValue };
/** Plugin-specific schemas are mandatory before values enter the typed boundary. */
export interface PluginContext {
  readonly attempt_id: string;
  readonly seed: string;
  readonly active_elapsed_ms: number;
}
export interface PluginResult {
  readonly status: 'running' | 'completed' | 'failed' | 'aborted';
  readonly outcome: string | null;
  readonly score: number | null;
}
export interface Step<State> {
  readonly state: State;
  readonly result: PluginResult;
}
export interface PluginLogic<Config, State, Command> {
  validateConfig(config: Config): true;
  validateState(config: Config, state: State): true;
  initialize(config: Config, context: PluginContext): State;
  reduce(config: Config, state: State, command: Command, context: PluginContext): Step<State>;
  result(config: Config, state: State): PluginResult;
  serialize(config: Config, state: State): string;
  restore(config: Config, snapshot: string, context: PluginContext): State;
}
export interface PluginViewHost<Config, State, Command> {
  readonly config: Config;
  readState(): State;
  readSession(): PluginSession;
  control(command: Exclude<PluginControl, 'start'>): Promise<void>;
  dispatch(command: Command): Promise<void>;
  subscribe(listener: () => void): () => void;
  assetUrl(resourceId: string): string;
  reportError(error: unknown): void;
}
export interface MountedPluginView {
  pause(): void;
  resume(): void;
  dispose(): void;
}
export interface PluginView<Config, State, Command> {
  mount(root: HTMLElement, host: PluginViewHost<Config, State, Command>): MountedPluginView;
}

/** Host controls use ActionRequest and the same revision/idempotency transaction. */
export type PluginControl = 'start' | 'pause' | 'resume' | 'exit' | 'retry';
export type PluginPhase = 'running' | 'paused' | 'completed' | 'failed' | 'aborted';
export interface PluginSession {
  readonly attempt_id: string;
  readonly phase: PluginPhase;
  readonly active_elapsed_ms: number;
}
export interface PluginControlAction {
  readonly kind: 'plugin_control';
  readonly action_id: string;
  readonly expected_revision: number;
  readonly target_id: string;
  readonly control: PluginControl;
  /** Null only for start; every other control binds the existing attempt. */
  readonly attempt_id: string | null;
}

import { AbstractAgent } from "@ag-ui/client";
import { EventType, type BaseEvent, type RunAgentInput } from "@ag-ui/core";
import { makeAgent } from "agent-core";
import { Observable, type Subscription } from "rxjs";
import { logChannel, safeError } from "./diagnostics";
import { failedReceipt, hasCompletedReply } from "./completed-reply";

type ChannelAgentFactory = (threadId: string) => AbstractAgent;

/**
 * Channel-only facade that keeps AG-UI transcript/state on the outer agent while
 * delegating each low-level run to a fresh BuiltInAgent instance.
 *
 * Channels may re-enter the same turn after tool results as soon as the previous
 * observable completes. BuiltInAgent clears its private abort controller later,
 * in its async cleanup, so reusing one instance can trip its reentry guard. This
 * facade leaves AbstractAgent.runAgent untouched and swaps only run(input), which
 * gives every invocation a clean inner agent without changing the shared web and
 * mobile makeAgent factory.
 */
export class ChannelRunAgent extends AbstractAgent {
  private activeInner: AbstractAgent | undefined;

  constructor(
    private agentFactory: ChannelAgentFactory = makeAgent,
    threadId?: string,
  ) {
    super({ threadId });
  }

  override run(input: RunAgentInput): Observable<BaseEvent> {
    return new Observable<BaseEvent>((subscriber) => {
      const receiptError = failedReceipt(input.messages);
      if (receiptError) {
        subscriber.next({ type: EventType.RUN_STARTED, threadId: input.threadId, runId: input.runId } as BaseEvent);
        subscriber.next({ type: EventType.RUN_ERROR, message: receiptError } as BaseEvent);
        subscriber.complete();
        return;
      }
      if (hasCompletedReply(input.messages)) {
        logChannel("reply.already_posted", { runId: input.runId });
        subscriber.next({ type: EventType.RUN_STARTED, threadId: input.threadId, runId: input.runId } as BaseEvent);
        subscriber.next({ type: EventType.RUN_FINISHED, threadId: input.threadId, runId: input.runId } as BaseEvent);
        subscriber.complete();
        return;
      }
      const started = Date.now();
      const meta = { runId: input.runId, messages: input.messages.length };
      logChannel("model.start", meta);
      let inner: AbstractAgent | undefined;
      let subscription: Subscription | undefined;

      const release = () => {
        if (this.activeInner === inner) {
          this.activeInner = undefined;
        }
      };

      try {
        inner = this.agentFactory(input.threadId);
        inner.threadId = input.threadId;
        this.activeInner = inner;
        subscription = inner.run(input).subscribe({
          next: (event) => {
            if (event.type === "TOOL_CALL_START") {
              logChannel("model.tool", { ...meta, tool: (event as BaseEvent & { toolCallName: string }).toolCallName });
            }
            if (event.type === "RUN_ERROR") {
              logChannel("model.error", { ...meta, elapsedMs: Date.now() - started, error: safeError((event as BaseEvent & { message: string }).message) });
            }
            subscriber.next(event);
          },
          error: (error) => {
            logChannel("model.error", { ...meta, elapsedMs: Date.now() - started, error: safeError(error) });
            release();
            subscriber.error(error);
          },
          complete: () => {
            logChannel("model.complete", { ...meta, elapsedMs: Date.now() - started });
            release();
            subscriber.complete();
          },
        });
      } catch (error) {
        release();
        subscriber.error(error);
      }

      return () => {
        subscription?.unsubscribe();
        inner?.abortRun();
        release();
      };
    });
  }

  override abortRun() {
    this.activeInner?.abortRun();
    super.abortRun();
  }

  override clone(): ChannelRunAgent {
    const cloned = super.clone() as ChannelRunAgent;
    cloned.agentFactory = this.agentFactory;
    cloned.activeInner = undefined;
    return cloned;
  }
}

export function makeChannelAgent(threadId: string) {
  // Keep the Slack surface focused on the explicitly registered channel tools.
  // Loading the entire Ambiguous workspace here exposes hundreds of MCP tools
  // on every mention, which can make small/cheap models stall before answering.
  // Ambiguous writes remain available through the web app's narrow,
  // approval-based integration.
  return new ChannelRunAgent(
    (innerThreadId) => makeAgent(innerThreadId, { workplace: false }),
    threadId,
  );
}

package com.aifuturetrade.asyncservice.controller;

import com.aifuturetrade.asyncservice.service.AsyncAgentService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;

/**
 * 异步代理控制器
 * 
 * 提供REST API接口来管理异步任务服务。
 */
@Slf4j
@RestController
@RequestMapping("/api/async")
public class AsyncAgentController {
    
    @Autowired
    private AsyncAgentService asyncAgentService;
    
    /**
     * 启动指定的异步任务
     * 
     * @param task 任务名称：market_tickers, price_refresh, market_symbol_offline, all
     * @param durationSeconds 可选，运行时长（秒）
     * @return 响应结果
     */
    @PostMapping("/task/{task}")
    public ResponseEntity<Map<String, Object>> startTask(
            @PathVariable(value = "task") String task,
            @RequestParam(value = "durationSeconds", required = false) Integer durationSeconds) {
        
        Map<String, Object> response = new HashMap<>();
        
        try {
            log.info("[AsyncAgentController] 🚀 收到启动任务请求: task={}, durationSeconds={}", 
                    task, durationSeconds);
            
            asyncAgentService.runTask(task, durationSeconds);
            
            log.info("[AsyncAgentController] ✅ 任务启动成功: task={}", task);
            
            response.put("success", true);
            response.put("message", "Task '" + task + "' started successfully");
            response.put("task", task);
            response.put("duration", durationSeconds);
            return ResponseEntity.ok(response);
            
        } catch (IllegalArgumentException e) {
            log.warn("[AsyncAgentController] ⚠️ 任务参数无效: task={}, error={}", task, e.getMessage());
            response.put("success", false);
            response.put("message", e.getMessage());
            return ResponseEntity.badRequest().body(response);
            
        } catch (Exception e) {
            log.error("[AsyncAgentController] ❌ 启动任务失败: task={}", task, e);
            response.put("success", false);
            response.put("message", "Failed to start task: " + e.getMessage());
            return ResponseEntity.internalServerError().body(response);
        }
    }
    
    /**
     * 停止所有任务
     * 
     * @return 响应结果
     */
    @PostMapping("/stop")
    public ResponseEntity<Map<String, Object>> stopAllTasks() {
        Map<String, Object> response = new HashMap<>();
        
        try {
            log.info("[AsyncAgentController] 🛑 收到停止所有任务请求");
            
            asyncAgentService.stopAllTasks();
            
            log.info("[AsyncAgentController] ✅ 所有任务已停止");
            
            response.put("success", true);
            response.put("message", "All tasks stopped successfully");
            return ResponseEntity.ok(response);
            
        } catch (Exception e) {
            log.error("[AsyncAgentController] ❌ 停止任务失败", e);
            response.put("success", false);
            response.put("message", "Failed to stop tasks: " + e.getMessage());
            return ResponseEntity.internalServerError().body(response);
        }
    }
    
    /**
     * 检查任务运行状态
     * 
     * @param task 任务名称
     * @return 响应结果
     */
    @GetMapping("/task/{task}/status")
    public ResponseEntity<Map<String, Object>> getTaskStatus(@PathVariable(value = "task") String task) {
        Map<String, Object> response = new HashMap<>();
        
        try {
            log.info("[AsyncAgentController] 📊 收到查询任务状态请求: task={}", task);
            
            boolean isRunning = asyncAgentService.isTaskRunning(task);
            
            log.info("[AsyncAgentController] 📊 任务状态: task={}, running={}", task, isRunning);
            
            response.put("success", true);
            response.put("task", task);
            response.put("running", isRunning);
            return ResponseEntity.ok(response);
            
        } catch (Exception e) {
            log.error("[AsyncAgentController] ❌ 获取任务状态失败: task={}", task, e);
            response.put("success", false);
            response.put("message", "Failed to get task status: " + e.getMessage());
            return ResponseEntity.internalServerError().body(response);
        }
    }
    
    /**
     * 获取所有任务状态
     * 
     * @return 响应结果
     */
    @GetMapping("/status")
    public ResponseEntity<Map<String, Object>> getAllTasksStatus() {
        Map<String, Object> response = new HashMap<>();
        
        try {
            log.info("[AsyncAgentController] 📊 收到查询所有任务状态请求");
            
            Map<String, Boolean> tasks = new HashMap<>();
            tasks.put("market_tickers", asyncAgentService.isTaskRunning("market_tickers"));
            tasks.put("price_refresh", asyncAgentService.isTaskRunning("price_refresh"));
            tasks.put("market_symbol_offline", asyncAgentService.isTaskRunning("market_symbol_offline"));
            tasks.put("all", asyncAgentService.isTaskRunning("all"));
            
            log.info("[AsyncAgentController] 📊 所有任务状态: market_tickers={}, price_refresh={}, market_symbol_offline={}, all={}",
                    tasks.get("market_tickers"), tasks.get("price_refresh"), 
                    tasks.get("market_symbol_offline"), tasks.get("all"));
            
            response.put("success", true);
            response.put("tasks", tasks);
            return ResponseEntity.ok(response);
            
        } catch (Exception e) {
            log.error("[AsyncAgentController] ❌ 获取所有任务状态失败", e);
            response.put("success", false);
            response.put("message", "Failed to get tasks status: " + e.getMessage());
            return ResponseEntity.internalServerError().body(response);
        }
    }
}

